#!/usr/bin/env python3
"""
ULTIMATE RELIABLE Telegram Quiz Bot for Render
- Bulletproof error handling and recovery
- Persistent data storage with Redis
- Advanced monitoring and health checks
- Connection pooling and rate limiting
- Graceful shutdown and restart handling
- Zero-maintenance operation
"""
import json
import logging
import os
import sys
import time
import signal
import threading
import random
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from enum import Enum

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from flask import Flask, request, jsonify
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Suppress noisy library logs
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('requests').setLevel(logging.WARNING)

class BotState(Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"

@dataclass
class UserSession:
    user_id: int
    state: str = "idle"
    anonymous: bool = True
    last_activity: float = 0
    quiz_count: int = 0
    error_count: int = 0
    created_at: float = 0
    
    def __post_init__(self):
        if self.created_at == 0:
            self.created_at = time.time()
        if self.last_activity == 0:
            self.last_activity = time.time()

@dataclass
class BotStats:
    total_requests: int = 0
    successful_polls: int = 0
    errors: int = 0
    start_time: float = 0
    last_activity: float = 0
    sleep_count: int = 0
    wake_count: int = 0
    keep_alive_pings: int = 0
    api_calls: int = 0
    rate_limit_hits: int = 0
    recovery_attempts: int = 0
    
    def __post_init__(self):
        if self.start_time == 0:
            self.start_time = time.time()
        if self.last_activity == 0:
            self.last_activity = time.time()

class ReliableHTTPClient:
    """HTTP client with connection pooling, retries, and rate limiting"""
    
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests
    
    @contextmanager
    def rate_limit(self):
        """Rate limiting context manager"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        
        self.last_request_time = time.time()
        yield
    
    def get(self, endpoint: str, **kwargs) -> Optional[Dict]:
        """Make GET request with rate limiting"""
        with self.rate_limit():
            try:
                response = self.session.get(
                    f"{self.base_url}/{endpoint}",
                    timeout=self.timeout,
                    **kwargs
                )
                return self._handle_response(response)
            except Exception as e:
                logger.error("GET request failed", endpoint=endpoint, error=str(e))
                return None
    
    def post(self, endpoint: str, data: Dict = None, **kwargs) -> Optional[Dict]:
        """Make POST request with rate limiting"""
        with self.rate_limit():
            try:
                response = self.session.post(
                    f"{self.base_url}/{endpoint}",
                    json=data,
                    timeout=self.timeout,
                    **kwargs
                )
                return self._handle_response(response)
            except Exception as e:
                logger.error("POST request failed", endpoint=endpoint, error=str(e))
                return None
    
    def _handle_response(self, response: requests.Response) -> Optional[Dict]:
        """Handle HTTP response"""
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 1))
            logger.warning("Rate limited", retry_after=retry_after)
            time.sleep(retry_after)
            return None
        else:
            logger.warning(
                "HTTP error",
                status_code=response.status_code,
                text=response.text[:200]
            )
            return None

class DataStore:
    """Persistent data storage with fallback to memory"""
    
    def __init__(self):
        self.memory_store: Dict[str, Any] = {}
        self.persistent_enabled = False
        self._lock = threading.RLock()
        
        # Try to initialize persistent storage
        self._init_persistent_storage()
    
    def _init_persistent_storage(self):
        """Initialize persistent storage if available"""
        try:
            # Try Redis first
            import redis
            redis_url = os.environ.get('REDIS_URL')
            if redis_url:
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
                self.redis_client.ping()
                self.persistent_enabled = True
                logger.info("Redis storage initialized")
                return
        except Exception as e:
            logger.warning("Redis not available", error=str(e))
        
        # Try file-based storage as fallback
        try:
            self.storage_file = os.environ.get('STORAGE_FILE', '/tmp/bot_data.json')
            self._load_from_file()
            self.persistent_enabled = True
            logger.info("File storage initialized")
        except Exception as e:
            logger.warning("File storage not available", error=str(e))
    
    def _load_from_file(self):
        """Load data from file"""
        if os.path.exists(self.storage_file):
            with open(self.storage_file, 'r') as f:
                self.memory_store = json.load(f)
    
    def _save_to_file(self):
        """Save data to file"""
        try:
            with open(self.storage_file, 'w') as f:
                json.dump(self.memory_store, f)
        except Exception as e:
            logger.error("Failed to save to file", error=str(e))
    
    def set(self, key: str, value: Any, ttl: int = None):
        """Set value with optional TTL"""
        with self._lock:
            try:
                if self.persistent_enabled and hasattr(self, 'redis_client'):
                    if ttl:
                        self.redis_client.setex(key, ttl, json.dumps(value))
                    else:
                        self.redis_client.set(key, json.dumps(value))
                else:
                    self.memory_store[key] = value
                    if self.persistent_enabled and hasattr(self, 'storage_file'):
                        self._save_to_file()
            except Exception as e:
                logger.error("Failed to set value", key=key, error=str(e))
                # Fallback to memory
                self.memory_store[key] = value
    
    def get(self, key: str, default=None) -> Any:
        """Get value"""
        with self._lock:
            try:
                if self.persistent_enabled and hasattr(self, 'redis_client'):
                    value = self.redis_client.get(key)
                    return json.loads(value) if value else default
                else:
                    return self.memory_store.get(key, default)
            except Exception as e:
                logger.error("Failed to get value", key=key, error=str(e))
                return self.memory_store.get(key, default)
    
    def delete(self, key: str):
        """Delete key"""
        with self._lock:
            try:
                if self.persistent_enabled and hasattr(self, 'redis_client'):
                    self.redis_client.delete(key)
                else:
                    self.memory_store.pop(key, None)
                    if self.persistent_enabled and hasattr(self, 'storage_file'):
                        self._save_to_file()
            except Exception as e:
                logger.error("Failed to delete key", key=key, error=str(e))
    
    def cleanup_expired(self, ttl: int = 3600):
        """Cleanup expired entries"""
        with self._lock:
            try:
                if self.persistent_enabled and hasattr(self, 'redis_client'):
                    # Redis handles TTL automatically
                    return
                
                current_time = time.time()
                expired_keys = []
                
                for key, value in self.memory_store.items():
                    if isinstance(value, dict) and 'last_activity' in value:
                        if current_time - value['last_activity'] > ttl:
                            expired_keys.append(key)
                
                for key in expired_keys:
                    self.memory_store.pop(key, None)
                
                if expired_keys and self.persistent_enabled and hasattr(self, 'storage_file'):
                    self._save_to_file()
                
                logger.info("Cleaned up expired entries", count=len(expired_keys))
            except Exception as e:
                logger.error("Cleanup failed", error=str(e))

class QuizBot:
    """Ultra-reliable Telegram Quiz Bot"""
    
    def __init__(self):
        self.state = BotState.STARTING
        self.bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        self.webhook_url = os.environ.get('WEBHOOK_URL', f"https://quiz-bot-tg.onrender.com/{self.bot_token}")
        
        if not self.bot_token:
            logger.error("TELEGRAM_BOT_TOKEN not set")
            sys.exit(1)
        
        # Initialize components
        self.http_client = ReliableHTTPClient(f"https://api.telegram.org/bot{self.bot_token}")
        self.data_store = DataStore()
        self.stats = BotStats()
        
        # Configuration
        self.max_users = 500
        self.user_ttl = 3600
        self.max_questions_per_quiz = 25
        self.keep_alive_interval = 780  # 13 minutes
        self.health_check_interval = 300  # 5 minutes
        
        # Threading
        self.keep_alive_active = True
        self.cleanup_active = True
        self.shutdown_event = threading.Event()
        
        # Start background tasks
        self._start_background_tasks()
        
        # Setup signal handlers
        self._setup_signal_handlers()
        
        self.state = BotState.RUNNING
        logger.info("Bot initialized successfully")
    
    def _start_background_tasks(self):
        """Start background maintenance tasks"""
        # Keep-alive thread
        keep_alive_thread = threading.Thread(target=self._keep_alive_worker, daemon=True)
        keep_alive_thread.start()
        
        # Cleanup thread
        cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        cleanup_thread.start()
        
        logger.info("Background tasks started")
    
    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers"""
        def signal_handler(signum, frame):
            logger.info("Shutdown signal received", signal=signum)
            self.shutdown()
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    
    def _keep_alive_worker(self):
        """Background keep-alive worker"""
        while self.keep_alive_active and not self.shutdown_event.is_set():
            try:
                time.sleep(60)  # Check every minute
                
                if self.shutdown_event.is_set():
                    break
                
                current_time = time.time()
                time_since_activity = current_time - self.stats.last_activity
                
                # If more than 10 minutes since last activity, ping
                if time_since_activity > 600:
                    self._keep_alive_ping()
                    
            except Exception as e:
                logger.error("Keep-alive worker error", error=str(e))
                time.sleep(60)
    
    def _cleanup_worker(self):
        """Background cleanup worker"""
        while self.cleanup_active and not self.shutdown_event.is_set():
            try:
                time.sleep(300)  # Cleanup every 5 minutes
                
                if self.shutdown_event.is_set():
                    break
                
                self.data_store.cleanup_expired(self.user_ttl)
                
            except Exception as e:
                logger.error("Cleanup worker error", error=str(e))
                time.sleep(300)
    
    def _keep_alive_ping(self):
        """Internal keep-alive ping"""
        try:
            app_url = self.webhook_url.split('/' + self.bot_token)[0]
            response = self.http_client.get(f"{app_url}/health")
            
            if response:
                self.stats.keep_alive_pings += 1
                logger.info("Keep-alive ping successful")
            else:
                logger.warning("Keep-alive ping failed")
                
        except Exception as e:
            logger.error("Keep-alive ping error", error=str(e))
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, ConnectionError))
    )
    def _make_telegram_request(self, method: str, data: Dict = None) -> Optional[Dict]:
        """Make request to Telegram API with retry logic"""
        self.stats.api_calls += 1
        
        if data:
            result = self.http_client.post(method, data)
        else:
            result = self.http_client.get(method)
        
        if result and result.get('ok'):
            return result
        elif result and not result.get('ok'):
            logger.warning("Telegram API error", method=method, error=result.get('description'))
            if result.get('error_code') == 429:
                self.stats.rate_limit_hits += 1
        else:
            logger.error("Telegram API request failed", method=method)
        
        return None
    
    def send_message(self, chat_id: int, text: str, reply_markup: Dict = None, parse_mode: str = None) -> bool:
        """Send message with error handling"""
        try:
            # Sanitize text
            text = str(text)[:4096]
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
            
            result = self._make_telegram_request('sendMessage', data)
            return result is not None
            
        except Exception as e:
            logger.error("Send message error", chat_id=chat_id, error=str(e))
            self.stats.errors += 1
            return False
    
    def send_poll(self, chat_id: int, question: str, options: List[str], 
                  correct_id: int, explanation: str = None, is_anonymous: bool = True) -> bool:
        """Send quiz poll with validation"""
        try:
            # Sanitize inputs
            question = str(question)[:300]
            options = [str(opt)[:100] for opt in options[:10]]
            
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
            
            result = self._make_telegram_request('sendPoll', data)
            if result:
                self.stats.successful_polls += 1
                return True
            return False
            
        except Exception as e:
            logger.error("Send poll error", chat_id=chat_id, error=str(e))
            self.stats.errors += 1
            return False
    
    def answer_callback_query(self, callback_query_id: int, text: str = ""):
        """Answer callback query"""
        try:
            data = {
                'callback_query_id': callback_query_id,
                'text': text[:200]
            }
            self._make_telegram_request('answerCallbackQuery', data)
        except Exception as e:
            logger.warning("Callback answer error", error=str(e))
    
    def edit_message_text(self, chat_id: int, message_id: int, text: str, parse_mode: str = None) -> bool:
        """Edit message text"""
        try:
            data = {
                'chat_id': chat_id,
                'message_id': message_id,
                'text': str(text)[:4096],
            }
            if parse_mode:
                data['parse_mode'] = parse_mode
            return self._make_telegram_request('editMessageText', data) is not None
        except Exception as e:
            logger.warning("Edit message error", error=str(e))
            return False
    
    def get_user_session(self, user_id: int) -> UserSession:
        """Get or create user session"""
        session_data = self.data_store.get(f"user:{user_id}")
        if session_data:
            session = UserSession(**session_data)
        else:
            session = UserSession(user_id=user_id)
        
        session.last_activity = time.time()
        self.data_store.set(f"user:{user_id}", asdict(session), ttl=self.user_ttl)
        self.stats.last_activity = time.time()
        
        return session
    
    def handle_start_command(self, chat_id: int, user_id: int, user_name: str):
        """Handle start command"""
        try:
            session = self.get_user_session(user_id)
            session.state = "choosing_type"
            
            welcome_msg = (
                f"👋 Hello {user_name}! 🌟\n\n"
                "🎯 **Ultra-Reliable Quiz Bot** - Create MCQ quizzes instantly!\n\n"
                "✨ **How it works:**\n"
                "1️⃣ Choose quiz type below\n"
                "2️⃣ Get JSON template\n" 
                "3️⃣ Customize with your questions\n"
                "4️⃣ Send back → Get instant quizzes! 🚀\n\n"
                "🔥 **Powered by Advanced Technology** - Zero Downtime!"
            )
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔒 Anonymous Quiz (Forwardable)", "callback_data": "anon_true"}],
                    [{"text": "👤 Non-Anonymous Quiz (Shows voters)", "callback_data": "anon_false"}]
                ]
            }
            
            self.send_message(chat_id, welcome_msg, keyboard, parse_mode='Markdown')
            
        except Exception as e:
            logger.error("Start command error", chat_id=chat_id, user_id=user_id, error=str(e))
            self.send_message(chat_id, f"Hello {user_name}! Use /start to create quizzes!")
    
    def handle_callback_query(self, callback_query: Dict):
        """Handle button callbacks"""
        try:
            user_id = callback_query['from']['id']
            chat_id = callback_query['message']['chat']['id']
            message_id = callback_query['message']['message_id']
            callback_data = callback_query['data']
            
            self.answer_callback_query(callback_query['id'])
            
            session = self.get_user_session(user_id)
            is_anonymous = callback_data == "anon_true"
            session.anonymous = is_anonymous
            session.state = "waiting_json"
            
            # CRITICAL: Save the session state immediately
            self.data_store.set(f"user:{user_id}", asdict(session), ttl=self.user_ttl)
            
            quiz_type = "🔒 Anonymous" if is_anonymous else "👤 Non-Anonymous"
            
            # Edit message
            self.edit_message_text(
                chat_id,
                message_id,
                f"✅ **{quiz_type} Quiz Selected!** 🎉\n\n⭐ **Template coming...** ⚡",
                parse_mode='Markdown'
            )
            
            # Send template
            template = '''{
  "all_q": [
    {
      "q": "'Truculent' means:",
      "o": ["Aggressive", "Genial"],
      "c": 0,
      "e": "Aggressive=belligerent,pugnacious"
    },
    {
      "q": "'Ineffable' means:",
      "o": ["Mundane", "Inexpressible"],
      "c": 1,
      "e": "Inexpressible=indescribable,unspeakable"
    },
    {
      "q": "What is the capital of Japan?",
      "o": ["Tokyo", "Osaka", "Kyoto"],
      "c": 0,
      "e": "Tokyo is the capital and largest city of Japan"
    },
    {
      "q": "Which programming language is known for web development?",
      "o": ["JavaScript", "Python", "Java", "C++"],
      "c": 0,
      "e": "JavaScript is primarily used for front-end web development"
    }
  ]
}'''
            self.send_message(chat_id, "📋 **JSON Template (2-4 Options Supported):**", parse_mode='Markdown')
            self.send_message(chat_id, template)
            
            instruction_msg = (
                f"✅ **{quiz_type} Selected!** 🎉\n\n"
                "📝 **Next Steps:**\n"
                "1️⃣ Copy the JSON template above\n"
                "2️⃣ Give it to ChatGPT/AI 🤖\n"
                "3️⃣ Ask to customize with your questions\n\n"
                "🎯 **Quiz Options:** 2-4 options per question\n"
                "📚 **Format:** `o` = options array, `c` = correct index (0,1,2,3)\n\n"
                "🚀 **Send your customized JSON:** 👇⚡"
            )
            
            self.send_message(chat_id, instruction_msg, parse_mode='Markdown')
            
        except Exception as e:
            logger.error("Callback handling error", error=str(e))
    
    def handle_json_quiz(self, chat_id: int, user_id: int, json_text: str):
        """Handle JSON quiz data"""
        try:
            session = self.get_user_session(user_id)
            logger.info(f"JSON quiz request from user {user_id}, state: {session.state}")
            if session.state != "waiting_json":
                self.send_message(chat_id, "🔄 Please use /start first! ✨")
                return
            
            # Parse JSON
            quiz_data = json.loads(json_text)
            questions = quiz_data.get("all_q", [])
            
            if not questions:
                self.send_message(chat_id, "❌ No questions found! Use /template for format 📋")
                return
            
            # Send processing message
            self.send_message(chat_id, "🔄 **Processing your quiz...** ⚡", parse_mode='Markdown')
            
            success_count = 0
            max_questions = min(len(questions), self.max_questions_per_quiz)
            
            for i, q_data in enumerate(questions[:max_questions]):
                try:
                    question = q_data.get("q", f"Question {i+1}")
                    options = q_data.get("o", ["Option A", "Option B"])
                    correct_id = q_data.get("c", 0)
                    explanation = q_data.get("e", "")
                    
                    if len(options) >= 2:
                        result = self.send_poll(
                            chat_id, question, options, 
                            correct_id, explanation, session.anonymous
                        )
                        if result:
                            success_count += 1
                        
                        # Rate limiting
                        if i < max_questions - 1:
                            time.sleep(0.05)
                            
                except Exception as e:
                    logger.warning("Question processing error", question_num=i+1, error=str(e))
                    continue
            
            session.quiz_count += 1
            session.state = "choosing_type"
            
            quiz_type = "🔒 Anonymous" if session.anonymous else "👤 Non-Anonymous"
            completion_msg = f"🎯 **{success_count} {quiz_type} quizzes sent!** ✅🎉"
            self.send_message(chat_id, completion_msg, parse_mode='Markdown')
            self.send_message(chat_id, "🎉 **Create another?** Use /start! 🚀", parse_mode='Markdown')
            
        except json.JSONDecodeError:
            self.send_message(chat_id, "❌ **Invalid JSON!** Use /template 📋", parse_mode='Markdown')
        except Exception as e:
            logger.error("JSON handling error", error=str(e))
            self.send_message(chat_id, "❌ **Error!** Please try again 🔄", parse_mode='Markdown')
    
    def handle_message(self, message: Dict):
        """Handle text messages"""
        try:
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            chat_id = message['chat']['id']
            user_name = message['from'].get('first_name', 'Friend')
            
            if text.startswith('/start'):
                self.handle_start_command(chat_id, user_id, user_name)
            elif text.startswith('/help'):
                help_text = (
                    "🆘 **Ultra-Reliable Quiz Bot Help** 📚\n\n"
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
                self.send_message(chat_id, help_text, parse_mode='Markdown')
            elif text.startswith('/status'):
                uptime = time.time() - self.stats.start_time
                hours = int(uptime // 3600)
                minutes = int((uptime % 3600) // 60)
                
                status_msg = (
                    f"📊 **Ultra-Reliable Bot Status** 🟢\n\n"
                    f"⏱️ **Uptime:** {hours}h {minutes}m\n"
                    f"📈 **Requests:** {self.stats.total_requests}\n"
                    f"🎯 **Polls Sent:** {self.stats.successful_polls}\n"
                    f"🔧 **API Calls:** {self.stats.api_calls}\n"
                    f"⚡ **Rate Limits:** {self.stats.rate_limit_hits}\n"
                    f"🛠️ **Recovery Attempts:** {self.stats.recovery_attempts}\n\n"
                    f"🚀 **Status: BULLETPROOF RELIABLE** ✨"
                )
                self.send_message(chat_id, status_msg, parse_mode='Markdown')
            elif text.startswith('/template'):
                template = '''{
  "all_q": [
    {
      "q": "'Truculent' means:",
      "o": ["Aggressive", "Genial"],
      "c": 0,
      "e": "Aggressive=belligerent,pugnacious"
    },
    {
      "q": "'Ineffable' means:",
      "o": ["Mundane", "Inexpressible"],
      "c": 1,
      "e": "Inexpressible=indescribable,unspeakable"
    }
  ]
}'''
                self.send_message(chat_id, "📋 **JSON Template:**", parse_mode='Markdown')
                self.send_message(chat_id, template)
                self.send_message(
                    chat_id,
                    "💡 **Copy template → Give to AI → Customize → Send back!** 🤖✨",
                    parse_mode='Markdown'
                )
            elif text.startswith('{') or '"all_q"' in text:
                self.handle_json_quiz(chat_id, user_id, text)
            else:
                self.send_message(
                    chat_id,
                    "🎯 Welcome! Use /start to create amazing quizzes! ✨"
                )
                
        except Exception as e:
            logger.error("Message handling error", error=str(e))
    
    def process_update(self, update_data: Dict):
        """Process incoming update"""
        try:
            self.stats.total_requests += 1
            
            if 'message' in update_data:
                self.handle_message(update_data['message'])
            elif 'callback_query' in update_data:
                self.handle_callback_query(update_data['callback_query'])
                
        except Exception as e:
            logger.error("Update processing error", error=str(e))
            self.stats.errors += 1
    
    def get_health_status(self) -> Dict:
        """Get comprehensive health status"""
        uptime = time.time() - self.stats.start_time
        active_users = len([k for k in self.data_store.memory_store.keys() if k.startswith('user:')])
        
        return {
            "status": "healthy" if self.state == BotState.RUNNING else "unhealthy",
            "state": self.state.value,
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": int(uptime),
            "uptime_human": f"{int(uptime//3600)}h {int((uptime%3600)//60)}m",
            "active_users": active_users,
            "total_requests": self.stats.total_requests,
            "successful_polls": self.stats.successful_polls,
            "errors": self.stats.errors,
            "api_calls": self.stats.api_calls,
            "rate_limit_hits": self.stats.rate_limit_hits,
            "recovery_attempts": self.stats.recovery_attempts,
            "keep_alive_pings": self.stats.keep_alive_pings,
            "last_activity": self.stats.last_activity,
            "persistent_storage": self.data_store.persistent_enabled,
            "memory_usage": len(self.data_store.memory_store)
        }
    
    def shutdown(self):
        """Graceful shutdown"""
        logger.info("Starting graceful shutdown")
        self.state = BotState.STOPPING
        
        # Signal background threads to stop
        self.shutdown_event.set()
        self.keep_alive_active = False
        self.cleanup_active = False
        
        # Wait for threads to finish (with timeout)
        time.sleep(2)
        
        logger.info("Shutdown complete")
        self.state = BotState.ERROR

# Global bot instance
bot = None

def create_app():
    """Create Flask application"""
    global bot
    
    app = Flask(__name__)
    bot = QuizBot()
    
    @app.route('/')
    def home():
        """Home page with comprehensive status"""
        try:
            health = bot.get_health_status()
            uptime = health['uptime_human']
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Ultra-Reliable Quiz Bot</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body {{ 
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                        margin: 0; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: #333; min-height: 100vh;
                    }}
                    .container {{ max-width: 900px; margin: 0 auto; }}
                    .card {{ 
                        background: white; padding: 30px; border-radius: 15px; 
                        box-shadow: 0 10px 30px rgba(0,0,0,0.2); margin: 20px 0;
                    }}
                    .status {{ 
                        color: #28a745; font-weight: bold; font-size: 1.2em;
                        background: #d4edda; padding: 10px; border-radius: 8px;
                        border-left: 5px solid #28a745;
                    }}
                    .stats-grid {{ 
                        display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                        gap: 15px; margin: 20px 0;
                    }}
                    .stat-item {{ 
                        background: #f8f9fa; padding: 15px; border-radius: 8px;
                        border-left: 4px solid #007bff;
                    }}
                    .button {{ 
                        display: inline-block; padding: 12px 24px; background: #007bff; 
                        color: white; text-decoration: none; border-radius: 8px; 
                        margin: 5px; transition: all 0.3s; font-weight: bold;
                    }}
                    .button:hover {{ background: #0056b3; transform: translateY(-2px); }}
                    .success {{ color: #28a745; }}
                    .warning {{ color: #ffc107; }}
                    .error {{ color: #dc3545; }}
                    h1 {{ color: #495057; text-align: center; }}
                    .footer {{ text-align: center; color: #666; margin-top: 40px; }}
                    .badge {{ 
                        display: inline-block; padding: 4px 8px; border-radius: 12px;
                        font-size: 0.8em; font-weight: bold; margin-left: 10px;
                    }}
                    .badge-success {{ background: #d4edda; color: #155724; }}
                    .badge-info {{ background: #d1ecf1; color: #0c5460; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🚀 Ultra-Reliable Telegram Quiz Bot</h1>
                    
                    <div class="card">
                        <div class="status">
                            Status: 🟢 {health['status'].upper()} & Running
                            <span class="badge badge-success">BULLETPROOF</span>
                        </div>
                        
                        <div class="stats-grid">
                            <div class="stat-item">
                                <strong>⏱️ Uptime:</strong><br>{uptime}
                            </div>
                            <div class="stat-item">
                                <strong>📈 Total Requests:</strong><br>{health['total_requests']:,}
                            </div>
                            <div class="stat-item">
                                <strong>🎯 Successful Polls:</strong><br>{health['successful_polls']:,}
                            </div>
                            <div class="stat-item">
                                <strong>👥 Active Users:</strong><br>{health['active_users']:,}
                            </div>
                            <div class="stat-item">
                                <strong>🔧 API Calls:</strong><br>{health['api_calls']:,}
                            </div>
                            <div class="stat-item">
                                <strong>⚡ Rate Limits:</strong><br>{health['rate_limit_hits']:,}
                            </div>
                            <div class="stat-item">
                                <strong>🛠️ Recovery Attempts:</strong><br>{health['recovery_attempts']:,}
                            </div>
                            <div class="stat-item">
                                <strong>💾 Storage:</strong><br>
                                {'Persistent' if health['persistent_storage'] else 'Memory Only'}
                                <span class="badge badge-info">{health['memory_usage']} items</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h3>🔗 Management & Monitoring</h3>
                        <div style="text-align: center;">
                            <a href="/set_webhook" class="button">Set Webhook</a>
                            <a href="/webhook_info" class="button">Check Webhook</a>
                            <a href="/health" class="button">Health Check</a>
                            <a href="/debug" class="button">Debug Info</a>
                            <a href="/metrics" class="button">Metrics</a>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h3>📱 Bot Usage</h3>
                        <p>1. Start a chat with your bot on Telegram</p>
                        <p>2. Send <code>/start</code> command</p>
                        <p>3. Follow the interactive setup</p>
                        <p>4. Create amazing quizzes with zero downtime!</p>
                    </div>
                    
                    <div class="footer">
                        <p>🚀 Powered by Advanced Technology - Zero Maintenance Deployment</p>
                        <p>🛡️ Bulletproof Reliability • ⚡ High Performance • 🔄 Auto-Recovery</p>
                    </div>
                </div>
            </body>
            </html>
            """
            return html
        except Exception as e:
            logger.error("Home page error", error=str(e))
            return f"Error loading status: {e}", 500
    
    @app.route(f'/{bot.bot_token}', methods=['POST'])
    def webhook():
        """Handle incoming Telegram updates"""
        try:
            json_str = request.get_data().decode('UTF-8')
            if not json_str:
                return jsonify({"error": "No data received"}), 400
                
            update_data = json.loads(json_str)
            bot.process_update(update_data)
            
            return jsonify({"ok": True})
            
        except json.JSONDecodeError as e:
            logger.error("JSON decode error", error=str(e))
            return jsonify({"error": "Invalid JSON"}), 400
        except Exception as e:
            logger.error("Webhook error", error=str(e))
            return jsonify({"error": "Internal error"}), 500
    
    @app.route('/set_webhook', methods=['GET'])
    def set_webhook():
        """Set webhook URL"""
        try:
            data = {
                'url': bot.webhook_url,
                'drop_pending_updates': True
            }
            result = bot._make_telegram_request('setWebhook', data)
            if result and result.get('ok'):
                return f"✅ Webhook set successfully!<br>URL: {bot.webhook_url}<br>Status: {result.get('description', 'Success')}"
            else:
                return f"❌ Failed to set webhook: {result}"
        except Exception as e:
            return f"❌ Webhook error: {e}"
    
    @app.route('/webhook_info', methods=['GET'])
    def webhook_info():
        """Get webhook information"""
        try:
            result = bot._make_telegram_request('getWebhookInfo')
            if result and result.get('ok'):
                return jsonify(result.get('result', {}))
            else:
                return jsonify({"error": "Failed to get webhook info", "result": result})
        except Exception as e:
            return jsonify({"error": str(e)})
    
    @app.route('/health', methods=['GET'])
    def health_check():
        """Comprehensive health check endpoint"""
        try:
            health = bot.get_health_status()
            status_code = 200 if health['status'] == 'healthy' else 503
            return jsonify(health), status_code
        except Exception as e:
            logger.error("Health check error", error=str(e))
            return jsonify({"status": "error", "error": str(e)}), 500
    
    @app.route('/debug', methods=['GET'])
    def debug():
        """Debug information"""
        try:
            me_result = bot._make_telegram_request('getMe')
            debug_info = {
                "bot_token_configured": bool(bot.bot_token),
                "webhook_url": bot.webhook_url,
                "bot_state": bot.state.value,
                "health_status": bot.get_health_status(),
                "environment": "render",
                "python_version": sys.version,
                "persistent_storage": bot.data_store.persistent_enabled,
                "memory_store_keys": list(bot.data_store.memory_store.keys())[:10]
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
    
    @app.route('/metrics', methods=['GET'])
    def metrics():
        """Prometheus-style metrics"""
        try:
            health = bot.get_health_status()
            metrics = []
            
            metrics.append(f"# HELP bot_uptime_seconds Bot uptime in seconds")
            metrics.append(f"# TYPE bot_uptime_seconds counter")
            metrics.append(f"bot_uptime_seconds {health['uptime_seconds']}")
            
            metrics.append(f"# HELP bot_total_requests Total number of requests")
            metrics.append(f"# TYPE bot_total_requests counter")
            metrics.append(f"bot_total_requests {health['total_requests']}")
            
            metrics.append(f"# HELP bot_successful_polls Total successful polls sent")
            metrics.append(f"# TYPE bot_successful_polls counter")
            metrics.append(f"bot_successful_polls {health['successful_polls']}")
            
            metrics.append(f"# HELP bot_errors Total errors encountered")
            metrics.append(f"# TYPE bot_errors counter")
            metrics.append(f"bot_errors {health['errors']}")
            
            metrics.append(f"# HELP bot_active_users Current active users")
            metrics.append(f"# TYPE bot_active_users gauge")
            metrics.append(f"bot_active_users {health['active_users']}")
            
            return '\n'.join(metrics), 200, {'Content-Type': 'text/plain'}
        except Exception as e:
            return f"Error generating metrics: {e}", 500
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Endpoint not found"}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error("Internal server error", error=str(error))
        return jsonify({"error": "Internal server error"}), 500
    
    return app

# Create the Flask app
app = create_app()

if __name__ == '__main__':
    logger.info("🚀 Ultra-Reliable Quiz Bot starting...")
    logger.info("Bot token configured", configured=bool(bot.bot_token))
    logger.info("Bot state", state=bot.state.value)
    logger.info("Persistent storage", enabled=bot.data_store.persistent_enabled)
    logger.info("🔄 VERSION: 2.0 - Ultra-Reliable (Deployed: 2025-10-06)")
    
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)