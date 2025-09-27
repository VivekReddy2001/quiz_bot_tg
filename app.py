#!/usr/bin/env python3
"""
ULTIMATE RELIABLE Telegram Quiz Bot for Render
Handles sleep issues, maximum uptime, bulletproof reliability
"""
import json
import logging
import os
import sys
import time
import requests
import threading
import random
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Suppress noisy library logs
for logger_name in ['urllib3', 'requests.packages.urllib3']:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Bot configuration
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable not set!")
    sys.exit(1)

TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', f"https://your-app-name.onrender.com/{BOT_TOKEN}")

# Simple in-memory storage with automatic cleanup
user_data = {}
bot_stats = {
    'total_requests': 0,
    'successful_polls': 0,
    'errors': 0,
    'start_time': time.time(),
    'last_activity': time.time(),
    'sleep_count': 0,
    'wake_count': 0,
    'keep_alive_pings': 0
}

# Configuration
MAX_USERS = 200
USER_TTL = 3600  # 1 hour
MAX_QUESTIONS_PER_QUIZ = 25
REQUEST_TIMEOUT = 30
KEEP_ALIVE_INTERVAL = 840  # 14 minutes (before 15min sleep)
HEALTH_CHECK_INTERVAL = 300  # 5 minutes

# Keep-alive system
keep_alive_active = True
last_keep_alive = time.time()

def cleanup_old_users():
    """Clean up old user data to prevent memory issues"""
    try:
        current_time = time.time()
        if len(user_data) <= MAX_USERS:
            return
            
        # Remove users older than TTL
        to_remove = []
        for user_id, data in user_data.items():
            if current_time - data.get('last_activity', 0) > USER_TTL:
                to_remove.append(user_id)
        
        for user_id in to_remove:
            user_data.pop(user_id, None)
            
        # If still too many, keep only the most recent
        if len(user_data) > MAX_USERS:
            sorted_users = sorted(
                user_data.items(),
                key=lambda x: x[1].get('last_activity', 0),
                reverse=True
            )
            user_data.clear()
            for user_id, data in sorted_users[:MAX_USERS//2]:
                user_data[user_id] = data
                
        logger.info(f"Cleaned up user data. Active users: {len(user_data)}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        # If cleanup fails, clear everything
        user_data.clear()

def make_telegram_request(method, data=None):
    """Make requests to Telegram API with retry logic"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            url = f"{TELEGRAM_API_URL}/{method}"
            if data:
                response = requests.post(url, json=data, timeout=REQUEST_TIMEOUT)
            else:
                response = requests.get(url, timeout=REQUEST_TIMEOUT)
                
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:  # Rate limited
                retry_after = int(response.headers.get('Retry-After', 1))
                logger.warning(f"Rate limited. Waiting {retry_after}s")
                time.sleep(retry_after)
                continue
            else:
                error_text = response.text[:200]
                logger.warning(f"Telegram API error: {response.status_code} - {error_text}")
                return None
                
        except requests.exceptions.Timeout:
            logger.warning(f"Request timeout (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error: {e} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            break
            
    bot_stats['errors'] += 1
    return None

def safe_send_message(chat_id, text, reply_markup=None, parse_mode=None):
    """Send message with error handling"""
    try:
        # Sanitize text
        text = str(text)[:4096]  # Telegram limit
        if not text.strip():
            text = "Empty message"
            
        data = {
            'chat_id': chat_id,
            'text': text
        }
        if parse_mode:
            data['parse_mode'] = parse_mode
        if reply_markup:
            data['reply_markup'] = reply_markup
            
        result = make_telegram_request('sendMessage', data)
        return result is not None
    except Exception as e:
        logger.error(f"Send message error: {e}")
        bot_stats['errors'] += 1
        return False

def safe_send_poll(chat_id, question, options, correct_id, explanation=None, is_anonymous=True):
    """Send quiz poll with validation"""
    try:
        # Sanitize inputs
        question = str(question)[:300]
        options = [str(opt)[:100] for opt in options[:10]]  # Max 10 options
        
        if len(options) < 2:
            options = ["Option A", "Option B"]
            
        if not isinstance(correct_id, int) or correct_id < 0 or correct_id >= len(options):
            correct_id = 0
            
        data = {
            'chat_id': chat_id,
            'question': question,
            'options': options,
            'type': 'quiz',
            'correct_option_id': correct_id,
            'is_anonymous': is_anonymous
        }
        
        if explanation:
            data['explanation'] = str(explanation)[:200]
            
        result = make_telegram_request('sendPoll', data)
        if result:
            bot_stats['successful_polls'] += 1
            return True
        return False
    except Exception as e:
        logger.error(f"Send poll error: {e}")
        bot_stats['errors'] += 1
        return False

def answer_callback_query(callback_query_id, text=""):
    """Answer callback query"""
    try:
        data = {
            'callback_query_id': callback_query_id,
            'text': text[:200]
        }
        make_telegram_request('answerCallbackQuery', data)
    except Exception as e:
        logger.warning(f"Callback answer error: {e}")

def edit_message_text(chat_id, message_id, text, parse_mode=None):
    """Edit message text"""
    try:
        data = {
            'chat_id': chat_id,
            'message_id': message_id,
            'text': str(text)[:4096],
        }
        if parse_mode:
            data['parse_mode'] = parse_mode
        return make_telegram_request('editMessageText', data) is not None
    except Exception as e:
        logger.warning(f"Edit message error: {e}")
        return False

def update_user_activity(user_id):
    """Update user activity timestamp"""
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]['last_activity'] = time.time()
    bot_stats['last_activity'] = time.time()

def keep_alive_ping():
    """Internal keep-alive ping to prevent sleeping"""
    global last_keep_alive
    try:
        # Self-ping to keep service awake
        current_time = time.time()
        if current_time - last_keep_alive > KEEP_ALIVE_INTERVAL:
            try:
                # Ping our own health endpoint
                app_url = WEBHOOK_URL.split('/' + BOT_TOKEN)[0]
                response = requests.get(f"{app_url}/health", timeout=10)
                if response.status_code == 200:
                    bot_stats['keep_alive_pings'] += 1
                    last_keep_alive = current_time
                    logger.info("Keep-alive ping successful")
                else:
                    logger.warning(f"Keep-alive ping failed: {response.status_code}")
            except Exception as e:
                logger.warning(f"Keep-alive ping error: {e}")
    except Exception as e:
        logger.error(f"Keep-alive system error: {e}")

def detect_sleep_wake():
    """Detect if service was sleeping and just woke up"""
    global last_keep_alive
    try:
        current_time = time.time()
        time_since_activity = current_time - bot_stats['last_activity']
        
        # If more than 20 minutes since last activity, likely woke from sleep
        if time_since_activity > 1200:  # 20 minutes
            bot_stats['sleep_count'] += 1
            bot_stats['wake_count'] += 1
            logger.info(f"Service woke up after {int(time_since_activity/60)} minutes")
            
            # Reset keep-alive timer
            last_keep_alive = current_time - KEEP_ALIVE_INTERVAL - 1
            
            # Immediate keep-alive ping
            keep_alive_ping()
            
            return True
        return False
    except Exception as e:
        logger.error(f"Sleep detection error: {e}")
        return False

def background_keep_alive():
    """Background thread to keep service alive"""
    while keep_alive_active:
        try:
            time.sleep(60)  # Check every minute
            keep_alive_ping()
        except Exception as e:
            logger.error(f"Background keep-alive error: {e}")
            time.sleep(60)

def start_keep_alive_system():
    """Start the keep-alive background system"""
    try:
        if not os.environ.get('DISABLE_KEEP_ALIVE'):
            thread = threading.Thread(target=background_keep_alive, daemon=True)
            thread.start()
            logger.info("Keep-alive system started")
    except Exception as e:
        logger.error(f"Failed to start keep-alive system: {e}")

@app.route('/')
def home():
    """Home page with bot status"""
    try:
        uptime = time.time() - bot_stats['start_time']
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Quiz Bot - Render Deployment</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                    margin: 0; padding: 20px; background: #f8f9fa; color: #333;
                }}
                .container {{ max-width: 800px; margin: 0 auto; }}
                .status {{ color: #28a745; font-weight: bold; }}
                .stats {{ 
                    background: white; padding: 20px; border-radius: 10px; 
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin: 20px 0;
                }}
                .button {{ 
                    display: inline-block; padding: 10px 20px; background: #007bff; 
                    color: white; text-decoration: none; border-radius: 5px; 
                    margin: 5px; transition: background 0.3s;
                }}
                .button:hover {{ background: #0056b3; }}
                .success {{ color: #28a745; }}
                .error {{ color: #dc3545; }}
                h1 {{ color: #495057; }}
                .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎯 Telegram Quiz Bot</h1>
                <p class="status">Status: 🟢 Online & Running on Render</p>
                
                <div class="stats">
                    <h3>📊 Statistics</h3>
                    <div class="grid">
                        <div><strong>Uptime:</strong> {hours}h {minutes}m</div>
                        <div><strong>Total Requests:</strong> {bot_stats['total_requests']}</div>
                        <div><strong>Successful Polls:</strong> {bot_stats['successful_polls']}</div>
                        <div><strong>Errors:</strong> {bot_stats['errors']}</div>
                        <div><strong>Active Users:</strong> {len(user_data)}</div>
                        <div><strong>Sleep/Wake Cycles:</strong> {bot_stats['sleep_count']}</div>
                        <div><strong>Keep-Alive Pings:</strong> {bot_stats['keep_alive_pings']}</div>
                        <div><strong>Last Activity:</strong> {int((time.time() - bot_stats['last_activity'])/60)}m ago</div>
                    </div>
                </div>
                
                <h3>🔗 Management</h3>
                <div class="grid">
                    <a href="/set_webhook" class="button">Set Webhook</a>
                    <a href="/webhook_info" class="button">Check Webhook</a>
                    <a href="/health" class="button">Health Check</a>
                    <a href="/debug" class="button">Debug Info</a>
                </div>
                
                <div class="stats">
                    <h3>📱 Bot Usage</h3>
                    <p>1. Start a chat with your bot on Telegram</p>
                    <p>2. Send <code>/start</code> command</p>
                    <p>3. Follow the interactive setup</p>
                    <p>4. Create amazing quizzes!</p>
                </div>
                
                <footer style="margin-top: 40px; color: #666; text-align: center;">
                    <p>🚀 Powered by Render - Zero Maintenance Deployment</p>
                </footer>
            </div>
        </body>
        </html>
        """
        return html
    except Exception as e:
        return f"Error loading status: {e}", 500

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    """Handle incoming Telegram updates"""
    try:
        bot_stats['total_requests'] += 1
        
        # Detect if we just woke up from sleep
        just_woke = detect_sleep_wake()
        if just_woke:
            logger.info("Service detected wake-up, initializing keep-alive")
        
        # Periodic cleanup
        if bot_stats['total_requests'] % 50 == 0:
            cleanup_old_users()
            
        json_str = request.get_data().decode('UTF-8')
        if not json_str:
            return jsonify({"error": "No data received"}), 400
            
        update_data = json.loads(json_str)
        
        if 'message' in update_data:
            handle_message(update_data)
        elif 'callback_query' in update_data:
            handle_callback(update_data)
            
        return jsonify({"ok": True})
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        bot_stats['errors'] += 1
        return jsonify({"error": "Invalid JSON"}), 400
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        bot_stats['errors'] += 1
        return jsonify({"error": "Internal error"}), 500

def handle_message(update_data):
    """Handle text messages"""
    try:
        message = update_data['message']
        user_id = message['from']['id']
        text = message.get('text', '').strip()
        chat_id = message['chat']['id']
        user_name = message['from'].get('first_name', 'Friend')
        
        update_user_activity(user_id)
        
        if text.startswith('/start'):
            handle_start(chat_id, user_id, user_name)
        elif text.startswith('/help'):
            handle_help(chat_id)
        elif text.startswith('/status'):
            handle_status(chat_id, user_id)
        elif text.startswith('/template'):
            handle_template(chat_id)
        elif text.startswith('{') or '"all_q"' in text:
            handle_json(chat_id, user_id, text)
        else:
            safe_send_message(
                chat_id,
                "🎯 Welcome! Use /start to create amazing quizzes! ✨"
            )
    except Exception as e:
        logger.error(f"Message handling error: {e}")

def handle_start(chat_id, user_id, user_name):
    """Handle start command"""
    try:
        user_data[user_id] = {
            "state": "choosing_type",
            "last_activity": time.time()
        }
        
        welcome_msg = (
            f"👋 Hello {user_name}! 🌟\n\n"
            "🎯 **Quiz Bot** - Create MCQ quizzes instantly!\n\n"
            "✨ **How it works:**\n"
            "1️⃣ Choose quiz type below\n"
            "2️⃣ Get JSON template\n" 
            "3️⃣ Customize with your questions\n"
            "4️⃣ Send back → Get instant quizzes! 🚀\n\n"
            "🔥 **Powered by Render** - Fast & Reliable!"
        )
        
        keyboard = {
            "inline_keyboard": [
                [{"text": "🔒 Anonymous Quiz (Forwardable)", "callback_data": "anon_true"}],
                [{"text": "👤 Non-Anonymous Quiz (Shows voters)", "callback_data": "anon_false"}]
            ]
        }
        
        result = safe_send_message(chat_id, welcome_msg, keyboard, parse_mode='Markdown')
        if not result:
            # Fallback without markdown
            safe_send_message(chat_id, f"Hello {user_name}! Choose your quiz type:", keyboard)
    except Exception as e:
        logger.error(f"Start handling error: {e}")

def handle_help(chat_id):
    """Handle help command"""
    help_text = (
        "🆘 **Quiz Bot Help** 📚\n\n"
        "🤖 **Commands:**\n"
        "• `/start` - Begin quiz creation\n"
        "• `/template` - Get JSON template\n"
        "• `/help` - Show this help\n"
        "• `/status` - Check bot status\n\n"
        "📚 **JSON Format:**\n"
        "• `all_q` - Questions array\n"
        "• `q` - Question text\n"
        "• `o` - Answer options (2-10 choices)\n"
        "• `c` - Correct answer (0=A, 1=B, etc.)\n"
        "• `e` - Explanation (optional)\n\n"
        "🚀 **Quick Start:** Use /start!"
    )
    
    result = safe_send_message(chat_id, help_text, parse_mode='Markdown')
    if not result:
        safe_send_message(chat_id, "Bot Help: Use /start to create quizzes!")

def handle_status(chat_id, user_id):
    """Handle status command"""
    try:
        uptime = time.time() - bot_stats['start_time']
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        
        user_type = "🔒 Anonymous" if user_data.get(user_id, {}).get('anonymous', True) else "👤 Non-Anonymous"
        
        status_msg = (
            f"📊 **Bot Status** 🟢\n\n"
            f"⏱️ **Uptime:** {hours}h {minutes}m\n"
            f"📈 **Requests:** {bot_stats['total_requests']}\n"
            f"🎯 **Polls Sent:** {bot_stats['successful_polls']}\n"
            f"👥 **Active Users:** {len(user_data)}\n"
            f"🎭 **Your Type:** {user_type}\n\n"
            f"🚀 **Ready to create quizzes!** ✨"
        )
        
        result = safe_send_message(chat_id, status_msg, parse_mode='Markdown')
        if not result:
            safe_send_message(chat_id, f"Bot Status: Online\nUptime: {hours}h {minutes}m")
    except Exception as e:
        logger.error(f"Status error: {e}")
        safe_send_message(chat_id, "Bot is running perfectly! 🚀")

def handle_template(chat_id):
    """Handle template command"""
    template = '{"all_q":[{"q":"What is the capital of France? 🇫🇷","o":["London","Paris","Berlin","Madrid"],"c":1,"e":"Paris is the capital and largest city of France 🗼"},{"q":"What is 2+2? 🔢","o":["3","4","5","6"],"c":1,"e":"Basic math: 2+2=4 ✅"}]}'
    
    safe_send_message(chat_id, "📋 **JSON Template:**", parse_mode='Markdown')
    safe_send_message(chat_id, template)
    safe_send_message(
        chat_id,
        "💡 **Copy template → Give to AI → Customize → Send back!** 🤖✨",
        parse_mode='Markdown'
    )

def handle_callback(update_data):
    """Handle button callbacks"""
    try:
        callback_query = update_data['callback_query']
        user_id = callback_query['from']['id']
        chat_id = callback_query['message']['chat']['id']
        message_id = callback_query['message']['message_id']
        callback_data = callback_query['data']
        
        answer_callback_query(callback_query['id'])
        update_user_activity(user_id)
        
        is_anonymous = callback_data == "anon_true"
        user_data[user_id] = {
            "state": "waiting_json",
            "anonymous": is_anonymous,
            "last_activity": time.time()
        }
        
        quiz_type = "🔒 Anonymous" if is_anonymous else "👤 Non-Anonymous"
        
        # Edit message
        edit_success = edit_message_text(
            chat_id,
            message_id,
            f"✅ **{quiz_type} Quiz Selected!** 🎉\n\n⭐ **Template coming...** ⚡",
            parse_mode='Markdown'
        )
        
        if not edit_success:
            safe_send_message(chat_id, f"{quiz_type} quiz selected!")
            
        # Send template
        template = '{"all_q":[{"q":"Sample question?","o":["Option A","Option B","Option C","Option D"],"c":1,"e":"Explanation here"}]}'
        safe_send_message(chat_id, "📋 **JSON Template:**", parse_mode='Markdown')
        safe_send_message(chat_id, template)
        
        instruction_msg = (
            f"✅ **{quiz_type} Selected!** 🎉\n\n"
            "📝 **Next Steps:**\n"
            "1️⃣ Copy the JSON template above\n"
            "2️⃣ Give it to ChatGPT/AI 🤖\n"
            "3️⃣ Ask to customize with your questions\n\n"
            "🚀 **Send your customized JSON:** 👇⚡"
        )
        
        result = safe_send_message(chat_id, instruction_msg, parse_mode='Markdown')
        if not result:
            safe_send_message(chat_id, f"{quiz_type} selected! Send your quiz JSON!")
    except Exception as e:
        logger.error(f"Callback handling error: {e}")

def handle_json(chat_id, user_id, json_text):
    """Handle JSON quiz data"""
    try:
        user_info = user_data.get(user_id, {})
        if user_info.get("state") != "waiting_json":
            safe_send_message(chat_id, "🔄 Please use /start first! ✨")
            return
            
        # Parse JSON
        quiz_data = json.loads(json_text)
        questions = quiz_data.get("all_q", [])
        
        if not questions:
            safe_send_message(chat_id, "❌ No questions found! Use /template for format 📋")
            return
            
        is_anonymous = user_info.get("anonymous", True)
        
        # Send processing message
        safe_send_message(chat_id, "🔄 **Processing your quiz...** ⚡", parse_mode='Markdown')
        
        success_count = 0
        max_questions = min(len(questions), MAX_QUESTIONS_PER_QUIZ)
        
        for i, q_data in enumerate(questions[:max_questions]):
            try:
                question = q_data.get("q", f"Question {i+1}")
                options = q_data.get("o", ["Option A", "Option B"])
                correct_id = q_data.get("c", 0)
                explanation = q_data.get("e", "")
                
                if len(options) >= 2:
                    result = safe_send_poll(
                        chat_id, question, options, 
                        correct_id, explanation, is_anonymous
                    )
                    if result:
                        success_count += 1
                    
                    # Rate limiting
                    if i < max_questions - 1:
                        time.sleep(0.05)
                        
            except Exception as e:
                logger.warning(f"Question {i+1} error: {e}")
                continue
                
        quiz_type = "🔒 Anonymous" if is_anonymous else "👤 Non-Anonymous"
        completion_msg = f"🎯 **{success_count} {quiz_type} quizzes sent!** ✅🎉"
        safe_send_message(chat_id, completion_msg, parse_mode='Markdown')
        
        # Reset for next quiz
        user_data[user_id] = {
            "state": "choosing_type",
            "last_activity": time.time()
        }
        
        safe_send_message(chat_id, "🎉 **Create another?** Use /start! 🚀", parse_mode='Markdown')
        
    except json.JSONDecodeError:
        safe_send_message(chat_id, "❌ **Invalid JSON!** Use /template 📋", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"JSON handling error: {e}")
        safe_send_message(chat_id, "❌ **Error!** Please try again 🔄", parse_mode='Markdown')

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """Set webhook URL"""
    try:
        data = {
            'url': WEBHOOK_URL,
            'drop_pending_updates': True
        }
        result = make_telegram_request('setWebhook', data)
        if result and result.get('ok'):
            return f"✅ Webhook set successfully!<br>URL: {WEBHOOK_URL}<br>Status: {result.get('description', 'Success')}"
        else:
            return f"❌ Failed to set webhook: {result}"
    except Exception as e:
        return f"❌ Webhook error: {e}"

@app.route('/webhook_info', methods=['GET'])
def webhook_info():
    """Get webhook information"""
    try:
        result = make_telegram_request('getWebhookInfo')
        if result and result.get('ok'):
            return jsonify(result.get('result', {}))
        else:
            return jsonify({"error": "Failed to get webhook info", "result": result})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "uptime_seconds": int(time.time() - bot_stats['start_time']),
        "active_users": len(user_data),
        "total_requests": bot_stats['total_requests']
    })

@app.route('/debug', methods=['GET'])
def debug():
    """Debug information"""
    try:
        me_result = make_telegram_request('getMe')
        debug_info = {
            "bot_token_configured": bool(BOT_TOKEN),
            "webhook_url": WEBHOOK_URL,
            "bot_stats": bot_stats,
            "active_users": len(user_data),
            "environment": "render",
            "python_version": sys.version
        }
        
        if me_result and me_result.get('ok'):
            bot_info = me_result.get('result', {})
            debug_info["bot_username"] = bot_info.get('username')
            debug_info["bot_name"] = bot_info.get('first_name')
            debug_info["bot_api_status"] = "✅ Working"
        else:
            debug_info["bot_api_status"] = f"❌ Error: {me_result}"
            
        return jsonify(debug_info)
    except Exception as e:
        return jsonify({"debug_error": str(e)})

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500

# Initialize keep-alive system on startup
start_keep_alive_system()

if __name__ == '__main__':
    logger.info("🚀 ULTIMATE RELIABLE Quiz Bot starting...")
    logger.info(f"Bot token configured: {'✅' if BOT_TOKEN else '❌'}")
    logger.info(f"Keep-alive system: {'✅ Active' if not os.environ.get('DISABLE_KEEP_ALIVE') else '❌ Disabled'}")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
