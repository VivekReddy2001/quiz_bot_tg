#!/usr/bin/env python3
"""
Ultra-Reliable External Keep-Alive Service for Quiz Bot
- Advanced monitoring and health checks
- Automatic failure detection and recovery
- Multiple endpoint monitoring
- Alert system integration
- Bulletproof reliability
"""
import requests
import time
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure advanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/keepalive.log')
    ]
)
logger = logging.getLogger(__name__)

class UltraReliableKeepAlive:
    """Ultra-reliable keep-alive service with advanced monitoring"""
    
    def __init__(self, bot_urls: List[str], telegram_token: str = None, alert_chat_id: str = None):
        self.bot_urls = [url.rstrip('/') for url in bot_urls]
        self.telegram_token = telegram_token
        self.alert_chat_id = alert_chat_id
        
        # Statistics
        self.stats = {
            'total_pings': 0,
            'successful_pings': 0,
            'failed_pings': 0,
            'start_time': time.time(),
            'last_success': None,
            'last_failure': None,
            'downtime_periods': [],
            'current_downtime_start': None,
            'consecutive_failures': 0,
            'recovery_attempts': 0
        }
        
        # HTTP client with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=5, pool_maxsize=10)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Configuration
        self.ping_interval = 780  # 13 minutes
        self.health_check_timeout = 30
        self.alert_threshold = 3  # Alert after 3 consecutive failures
        self.max_consecutive_failures = 10
        
        logger.info(f"Keep-alive service initialized for {len(self.bot_urls)} bots")
    
    def ping_bot(self, bot_url: str) -> tuple[bool, Optional[Dict]]:
        """Ping a single bot with comprehensive health check"""
        try:
            # Try health endpoint first
            response = self.session.get(
                f"{bot_url}/health", 
                timeout=self.health_check_timeout
            )
            
            if response.status_code == 200:
                health_data = response.json()
                uptime = health_data.get('uptime_seconds', 0)
                status = health_data.get('status', 'unknown')
                
                logger.info(
                    f"✅ {bot_url} - Healthy | Uptime: {uptime}s | Status: {status}"
                )
                
                # Try additional endpoints for comprehensive check
                self._check_additional_endpoints(bot_url)
                
                return True, health_data
            else:
                logger.warning(f"❌ {bot_url} - HTTP {response.status_code}")
                return False, None
                
        except requests.exceptions.Timeout:
            logger.warning(f"⏰ {bot_url} - Timeout")
            return False, None
        except requests.exceptions.ConnectionError:
            logger.warning(f"🔌 {bot_url} - Connection Error")
            return False, None
        except Exception as e:
            logger.error(f"💥 {bot_url} - Error: {e}")
            return False, None
    
    def _check_additional_endpoints(self, bot_url: str):
        """Check additional endpoints for comprehensive monitoring"""
        endpoints_to_check = [
            ('/debug', 'Debug Info'),
            ('/metrics', 'Metrics'),
            ('/webhook_info', 'Webhook Info')
        ]
        
        for endpoint, description in endpoints_to_check:
            try:
                response = self.session.get(
                    f"{bot_url}{endpoint}", 
                    timeout=10
                )
                if response.status_code == 200:
                    logger.debug(f"✅ {description} endpoint healthy")
                else:
                    logger.warning(f"⚠️ {description} endpoint: HTTP {response.status_code}")
            except Exception as e:
                logger.debug(f"⚠️ {description} endpoint error: {e}")
    
    def send_alert(self, message: str, severity: str = "warning"):
        """Send alert via Telegram"""
        if not self.telegram_token or not self.alert_chat_id:
            logger.warning(f"🚨 Alert: {message}")
            return
        
        try:
            emoji_map = {
                "info": "ℹ️",
                "warning": "⚠️",
                "error": "🚨",
                "success": "✅"
            }
            
            emoji = emoji_map.get(severity, "📢")
            
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = {
                'chat_id': self.alert_chat_id,
                'text': f"{emoji} Keep-Alive Alert\n\n{message}\n\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                'parse_mode': 'HTML'
            }
            
            response = self.session.post(url, json=data, timeout=10)
            if response.status_code == 200:
                logger.info("📱 Alert sent successfully")
            else:
                logger.warning(f"📱 Alert send failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"📱 Alert send error: {e}")
    
    def handle_failure(self, bot_url: str, error: str):
        """Handle bot failure with advanced logic"""
        self.stats['failed_pings'] += 1
        self.stats['last_failure'] = datetime.now()
        self.stats['consecutive_failures'] += 1
        
        # Start downtime tracking if not already started
        if not self.stats['current_downtime_start']:
            self.stats['current_downtime_start'] = datetime.now()
            logger.error(f"🔴 Downtime started for {bot_url}: {error}")
            
            # Send initial alert
            if self.stats['consecutive_failures'] >= self.alert_threshold:
                self.send_alert(
                    f"Bot {bot_url} is DOWN!\nError: {error}\nConsecutive failures: {self.stats['consecutive_failures']}",
                    "error"
                )
        
        # Escalation alerts
        if self.stats['consecutive_failures'] == 5:
            self.send_alert(
                f"Bot {bot_url} still DOWN after 5 attempts!\nDuration: {self._get_downtime_duration()}",
                "error"
            )
        elif self.stats['consecutive_failures'] == 10:
            self.send_alert(
                f"CRITICAL: Bot {bot_url} DOWN for extended period!\nDuration: {self._get_downtime_duration()}",
                "error"
            )
    
    def handle_success(self, bot_url: str, health_data: Dict):
        """Handle successful ping"""
        self.stats['successful_pings'] += 1
        self.stats['last_success'] = datetime.now()
        
        # If we were in downtime, record recovery
        if self.stats['current_downtime_start']:
            downtime_duration = datetime.now() - self.stats['current_downtime_start']
            self.stats['downtime_periods'].append({
                'start': self.stats['current_downtime_start'],
                'end': datetime.now(),
                'duration_minutes': downtime_duration.total_seconds() / 60,
                'bot_url': bot_url
            })
            self.stats['current_downtime_start'] = None
            self.stats['recovery_attempts'] += 1
            
            logger.info(f"🟢 {bot_url} recovered after {downtime_duration.total_seconds()/60:.1f} minutes")
            
            # Send recovery alert
            self.send_alert(
                f"✅ Bot {bot_url} RECOVERED!\nDowntime: {downtime_duration.total_seconds()/60:.1f} minutes\nUptime: {health_data.get('uptime_seconds', 0)}s",
                "success"
            )
        
        # Reset consecutive failures
        if self.stats['consecutive_failures'] > 0:
            logger.info(f"🔄 {bot_url} - Consecutive failures reset: {self.stats['consecutive_failures']} -> 0")
            self.stats['consecutive_failures'] = 0
    
    def _get_downtime_duration(self) -> str:
        """Get current downtime duration"""
        if self.stats['current_downtime_start']:
            duration = datetime.now() - self.stats['current_downtime_start']
            return f"{duration.total_seconds()/60:.1f} minutes"
        return "0 minutes"
    
    def get_uptime_percentage(self) -> float:
        """Calculate overall uptime percentage"""
        if self.stats['total_pings'] == 0:
            return 100.0
        return (self.stats['successful_pings'] / self.stats['total_pings']) * 100
    
    def print_comprehensive_stats(self):
        """Print comprehensive monitoring statistics"""
        uptime_pct = self.get_uptime_percentage()
        service_uptime = time.time() - self.stats['start_time']
        
        print(f"\n{'='*60}")
        print(f"📊 ULTRA-RELIABLE KEEP-ALIVE STATISTICS")
        print(f"{'='*60}")
        print(f"Service Uptime: {service_uptime/3600:.1f} hours")
        print(f"Total Pings: {self.stats['total_pings']}")
        print(f"Successful: {self.stats['successful_pings']}")
        print(f"Failed: {self.stats['failed_pings']}")
        print(f"Success Rate: {uptime_pct:.2f}%")
        print(f"Consecutive Failures: {self.stats['consecutive_failures']}")
        print(f"Recovery Attempts: {self.stats['recovery_attempts']}")
        
        if self.stats['last_success']:
            print(f"Last Success: {self.stats['last_success'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        if self.stats['last_failure']:
            print(f"Last Failure: {self.stats['last_failure'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        if self.stats['current_downtime_start']:
            print(f"Current Downtime: {self._get_downtime_duration()}")
        
        print(f"Total Downtime Periods: {len(self.stats['downtime_periods'])}")
        
        # Show recent downtime periods
        if self.stats['downtime_periods']:
            print(f"\n🕐 Recent Downtime Periods:")
            for period in self.stats['downtime_periods'][-5:]:
                print(f"  {period['start'].strftime('%m-%d %H:%M')} - {period['end'].strftime('%H:%M')} ({period['duration_minutes']:.1f}m) - {period.get('bot_url', 'Unknown')}")
        
        print(f"{'='*60}\n")
    
    def ping_all_bots(self) -> bool:
        """Ping all configured bots"""
        all_success = True
        
        for bot_url in self.bot_urls:
            self.stats['total_pings'] += 1
            success, health_data = self.ping_bot(bot_url)
            
            if success:
                self.handle_success(bot_url, health_data or {})
            else:
                self.handle_failure(bot_url, "Ping failed")
                all_success = False
            
            # Small delay between pings
            time.sleep(1)
        
        return all_success
    
    def run_forever(self):
        """Main monitoring loop with advanced error handling"""
        logger.info("🚀 Ultra-Reliable Keep-Alive Service Starting...")
        logger.info(f"Monitoring {len(self.bot_urls)} bots:")
        for i, url in enumerate(self.bot_urls, 1):
            logger.info(f"  {i}. {url}")
        
        ping_cycle = 0
        
        try:
            while True:
                ping_cycle += 1
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                logger.info(f"📡 Ping Cycle #{ping_cycle} at {current_time}")
                
                # Ping all bots
                all_success = self.ping_all_bots()
                
                # Print stats every 10 cycles
                if ping_cycle % 10 == 0:
                    self.print_comprehensive_stats()
                
                # Emergency shutdown if too many failures
                if self.stats['consecutive_failures'] >= self.max_consecutive_failures:
                    logger.critical(f"🚨 EMERGENCY: Too many consecutive failures ({self.stats['consecutive_failures']})")
                    self.send_alert(
                        f"🚨 EMERGENCY SHUTDOWN!\nToo many consecutive failures: {self.stats['consecutive_failures']}\nService may need manual intervention!",
                        "error"
                    )
                    break
                
                # Sleep before next ping
                logger.info(f"😴 Sleeping for {self.ping_interval/60:.1f} minutes...")
                time.sleep(self.ping_interval)
                
        except KeyboardInterrupt:
            logger.info("🛑 Keep-alive service stopped by user")
        except Exception as e:
            logger.critical(f"💥 Critical error in main loop: {e}")
            self.send_alert(f"💥 Keep-alive service crashed: {e}", "error")
        finally:
            self.print_comprehensive_stats()
            logger.info("🛑 Keep-alive service shutdown complete")

def main():
    """Main function with configuration"""
    # Configuration - Update these values
    BOT_URLS = [
        "https://quiz-bot-tg.onrender.com",  # Your main bot URL
        # Add more bot URLs here if you have multiple instances
    ]
    
    # Optional: Telegram alert configuration
    TELEGRAM_TOKEN = os.environ.get('KEEPALIVE_TELEGRAM_TOKEN')  # Optional
    ALERT_CHAT_ID = os.environ.get('KEEPALIVE_ALERT_CHAT_ID')   # Optional
    
    # Validate configuration
    if not BOT_URLS or not BOT_URLS[0] or BOT_URLS[0] == "https://your-quiz-bot.onrender.com":
        logger.error("❌ Please update BOT_URLS with your actual bot URL!")
        sys.exit(1)
    
    # Create and run keep-alive service
    keepalive = UltraReliableKeepAlive(BOT_URLS, TELEGRAM_TOKEN, ALERT_CHAT_ID)
    keepalive.run_forever()

if __name__ == "__main__":
    main()
