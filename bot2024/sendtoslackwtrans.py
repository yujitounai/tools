import feedparser
import sqlite3
import requests
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, request, render_template, redirect, url_for
import threading
import os
from datetime import datetime
import re
from googletrans import Translator  # Google翻訳API（googletransライブラリを利用）

# ロギングの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# データベースを設定する
DB_PATH = 'app.db'
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

# テーブルの作成とマイグレーション
def init_db():
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            slack_token TEXT,
            slack_channel TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS rss_urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS sent_urls (
            url TEXT PRIMARY KEY
        )
    ''')

    # settingsテーブルに新しいカラムを追加する
    c.execute("PRAGMA table_info(settings)")
    columns = [column[1] for column in c.fetchall()]
    if 'schedule_interval' not in columns:
        c.execute('ALTER TABLE settings ADD COLUMN schedule_interval INTEGER DEFAULT 30')
        logging.info("schedule_intervalカラムをsettingsテーブルに追加しました。")
    if 'last_run_time' not in columns:
        c.execute('ALTER TABLE settings ADD COLUMN last_run_time TEXT')
        logging.info("last_run_timeカラムをsettingsテーブルに追加しました。")

    conn.commit()

init_db()

def contains_japanese(text):
    """日本語が含まれているかどうかを判定する"""
    return bool(re.search('[\u3040-\u30FF\u4E00-\u9FFF]', text))

def translate_to_japanese(text):
    """英語のテキストを日本語に翻訳する"""
    translator = Translator()
    try:
        result = translator.translate(text, src='en', dest='ja')
        return result.text
    except Exception as e:
        logging.error(f"翻訳に失敗しました: {e}")
        return text  # 翻訳に失敗した場合は元のテキストを返す

def get_settings():
    c.execute('SELECT slack_token, slack_channel, schedule_interval, last_run_time FROM settings WHERE id = 1')
    return c.fetchone()

def get_keywords():
    c.execute('SELECT keyword FROM keywords')
    return [row[0] for row in c.fetchall()]

def get_rss_urls():
    c.execute('SELECT url FROM rss_urls')
    return [row[0] for row in c.fetchall()]

def set_settings(slack_token, slack_channel, schedule_interval):
    c.execute('''
        INSERT OR REPLACE INTO settings (id, slack_token, slack_channel, schedule_interval)
        VALUES (1, ?, ?, ?)
    ''', (slack_token, slack_channel, schedule_interval))
    conn.commit()
    # スケジュールを更新
    update_scheduler(schedule_interval)

def update_last_run_time():
    last_run_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('UPDATE settings SET last_run_time = ? WHERE id = 1', (last_run_time,))
    conn.commit()

def add_keyword(keyword):
    try:
        c.execute('INSERT INTO keywords (keyword) VALUES (?)', (keyword,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def delete_keyword(keyword):
    c.execute('DELETE FROM keywords WHERE keyword = ?', (keyword,))
    conn.commit()

def add_rss_url(url):
    try:
        c.execute('INSERT INTO rss_urls (url) VALUES (?)', (url,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def delete_rss_url(url):
    c.execute('DELETE FROM rss_urls WHERE url = ?', (url,))
    conn.commit()

def is_url_sent(url):
    c.execute('SELECT 1 FROM sent_urls WHERE url = ?', (url,))
    return c.fetchone() is not None

def mark_url_as_sent(url):
    c.execute('INSERT OR IGNORE INTO sent_urls (url) VALUES (?)', (url,))
    conn.commit()

def send_to_slack(message, slack_token, slack_channel):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {slack_token}',
    }
    data = {
        'channel': slack_channel,
        'text': message,
    }
    response = requests.post('https://slack.com/api/chat.postMessage', json=data, headers=headers)
    if not response.json().get('ok'):
        logging.error(f"Slackへのメッセージ送信に失敗しました: {response.text}")

def process_feeds():
    logging.info("========== フィード処理開始 ==========")
    settings = get_settings()
    if not settings:
        logging.error("Slackの設定が未設定です。")
        return
    slack_token, slack_channel, _, _ = settings
    keywords = get_keywords()
    rss_urls = get_rss_urls()
    logging.info(f"読み込んだキーワード: {keywords}")
    logging.info(f"読み込んだRSSフィードのURL: {rss_urls}")
    new_items = []
    for url in rss_urls:
        logging.info(f"フィードを取得中: {url}")
        feed = feedparser.parse(url)
        for entry in feed.entries:
            link = entry.link
            logging.info(f"記事のURLを処理中: {link}")
            if is_url_sent(link):
                logging.info("既に処理済みのURLです。スキップします。")
                continue
            summary = entry.summary if 'summary' in entry else ''
            title = entry.title if 'title' in entry else ''
            content = f"{title} {summary}"
            # 空文字のキーワードを除外
            keywords_filtered = [kw for kw in keywords if kw]
            matched_keywords = [kw for kw in keywords_filtered if kw in content]
            if matched_keywords:
                matched_keywords_str = ', '.join(matched_keywords)
                message_summary = summary

                # 日本語が含まれていない場合は翻訳
                if not contains_japanese(content):
                    logging.info("日本語が含まれていません。翻訳を実行します。")
                    translated_summary = translate_to_japanese(summary)
                    message_summary = translated_summary  # 翻訳した内容を使用

                message = f"*タイトル:* {title}\n*URL:* {link}\n*概要:* {message_summary}\n*合致したキーワード:* {matched_keywords_str}"
                new_items.append((link, message))
                logging.info(f"キーワードに合致しました: {matched_keywords_str}")
            else:
                logging.info("キーワードに合致しませんでした。")
            # URLを送信済みにマーク（ここを変更）
            mark_url_as_sent(link)
    # 全てのフィードを処理した後、Slackに送信する
    for link, message in new_items:
        send_to_slack(message, slack_token, slack_channel)
    update_last_run_time()
    logging.info("========== フィード処理終了 ==========\n")

# スケジューラを設定する
scheduler = BackgroundScheduler()

def update_scheduler(interval_minutes):
    scheduler.remove_all_jobs()
    scheduler.add_job(process_feeds, 'interval', minutes=interval_minutes)
    logging.info(f"スケジュールを更新しました。次回実行までの間隔: {interval_minutes} 分")

# 初期設定のスケジュールを開始
initial_settings = get_settings()
if initial_settings and initial_settings[2]:
    update_scheduler(initial_settings[2])
else:
    update_scheduler(30)  # デフォルトは30分

scheduler.start()

# Flaskアプリケーションを作成する
app = Flask(__name__)

@app.route('/')
def index():
    settings = get_settings()
    keywords = get_keywords()
    rss_urls = get_rss_urls()
    return render_template('index.html', settings=settings, keywords=keywords, rss_urls=rss_urls)

@app.route('/update_settings', methods=['POST'])
def update_settings():
    slack_token = request.form.get('slack_token')
    slack_channel = request.form.get('slack_channel')
    schedule_interval = int(request.form.get('schedule_interval', 30))
    set_settings(slack_token, slack_channel, schedule_interval)
    return redirect(url_for('index'))

@app.route('/add_keyword', methods=['POST'])
def add_keyword_route():
    keyword = request.form.get('keyword').strip()
    if keyword:
        success = add_keyword(keyword)
        if success:
            return redirect(url_for('index'))
        else:
            return 'キーワードの追加に失敗しました（重複している可能性があります）。<br><a href="/">戻る</a>'
    else:
        return '無効なキーワードです。<br><a href="/">戻る</a>'

@app.route('/delete_keyword', methods=['POST'])
def delete_keyword_route():
    keyword = request.form.get('keyword')
    delete_keyword(keyword)
    return redirect(url_for('index'))

@app.route('/add_rss_url', methods=['POST'])
def add_rss_url_route():
    url = request.form.get('rss_url').strip()
    if url:
        success = add_rss_url(url)
        if success:
            return redirect(url_for('index'))
        else:
            return 'RSS URLの追加に失敗しました（重複している可能性があります）。<br><a href="/">戻る</a>'
    else:
        return '無効なURLです。<br><a href="/">戻る</a>'

@app.route('/delete_rss_url', methods=['POST'])
def delete_rss_url_route():
    url = request.form.get('rss_url')
    delete_rss_url(url)
    return redirect(url_for('index'))

@app.route('/process_feeds')
def process_feeds_api():
    process_feeds()
    return 'Feeds processed', 200

if __name__ == '__main__':
    # テンプレートフォルダのパスを設定
    app.template_folder = os.path.join(os.path.dirname(__file__), 'templates')
    # 静的ファイルのパスを設定
    app.static_folder = os.path.join(os.path.dirname(__file__), 'static')
    # Flaskアプリを別スレッドで実行する
    threading.Thread(target=app.run, kwargs={'use_reloader': False}).start()
    # メインスレッドを維持する（CPU使用率を下げるために変更）
    try:
        threading.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        conn.close()