#!/usr/bin/env python3
"""
Advanced Bot Monitoring System
Monitors bot health, uptime, and sends alerts
"""
import requests
import time
import json
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BotMonitor:
    def __init__(self, bot_url, telegram_token=None, alert_chat_id=None):
        self.bot_url = bot_url.rstrip('/')
        self.telegram_token = telegram_token
        self.alert_chat_id = alert_chat_id
        self.stats = {
            'total_checks': 0,
            'successful_checks': 0,
            'failed_checks': 0,
            'last_success': None,
            'last_failure': None,
            'downtime_periods': [],
            'current_downtime_start': None
        }
    
    def check_bot_health(self):
        """Check if bot is responding"""
        try:
            response = requests.get(f"{self.bot_url}/health", timeout=30)
            self.stats['total_checks'] += 1
            
            if response.status_code == 200:
                data = response.json()
                self.stats['successful_checks'] += 1
                self.stats['last_success'] = datetime.now()
                
                # If we were in downtime, record the end
                if self.stats['current_downtime_start']:
                    downtime_duration = datetime.now() - self.stats['current_downtime_start']
                    self.stats['downtime_periods'].append({
                        'start': self.stats['current_downtime_start'],
                        'end': datetime.now(),
                        'duration_minutes': downtime_duration.total_seconds() / 60
                    })
                    self.stats['current_downtime_start'] = None
                    logger.info(f"🟢 Bot recovered after {downtime_duration.total_seconds()/60:.1f} minutes")
                
                logger.info(f"✅ Bot healthy - Uptime: {data.get('uptime_seconds', 0)}s")
                return True, data
            else:
                self.handle_failure(f"HTTP {response.status_code}")
                return False, None
                
        except requests.exceptions.Timeout:
            self.handle_failure("Timeout")
            return False, None
        except Exception as e:
            self.handle_failure(str(e))
            return False, None
    
    def handle_failure(self, error):
        """Handle bot failure"""
        self.stats['failed_checks'] += 1
        self.stats['last_failure'] = datetime.now()
        
        # Start downtime tracking if not already started
        if not self.stats['current_downtime_start']:
            self.stats['current_downtime_start'] = datetime.now()
            logger.warning(f"🔴 Bot downtime started: {error}")
            self.send_alert(f"🚨 Bot is DOWN: {error}")
        
        logger.error(f"❌ Bot check failed: {error}")
    
    def send_alert(self, message):
        """Send alert via Telegram"""
        if not self.telegram_token or not self.alert_chat_id:
            return
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = {
                'chat_id': self.alert_chat_id,
                'text': f"🤖 Quiz Bot Alert\n\n{message}\n\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                'parse_mode': 'HTML'
            }
            response = requests.post(url, json=data, timeout=10)
            if response.status_code == 200:
                logger.info("📱 Alert sent successfully")
            else:
                logger.warning(f"📱 Alert send failed: {response.status_code}")
        except Exception as e:
            logger.error(f"📱 Alert send error: {e}")
    
    def get_uptime_percentage(self):
        """Calculate uptime percentage"""
        if self.stats['total_checks'] == 0:
            return 100.0
        return (self.stats['successful_checks'] / self.stats['total_checks']) * 100
    
    def print_stats(self):
        """Print monitoring statistics"""
        uptime_pct = self.get_uptime_percentage()
        
        print(f"\n📊 Bot Monitoring Statistics")
        print(f"{'='*40}")
        print(f"Total Checks: {self.stats['total_checks']}")
        print(f"Successful: {self.stats['successful_checks']}")
        print(f"Failed: {self.stats['failed_checks']}")
        print(f"Uptime: {uptime_pct:.2f}%")
        
        if self.stats['last_success']:
            print(f"Last Success: {self.stats['last_success'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        if self.stats['last_failure']:
            print(f"Last Failure: {self.stats['last_failure'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        if self.stats['current_downtime_start']:
            downtime_duration = datetime.now() - self.stats['current_downtime_start']
            print(f"Current Downtime: {downtime_duration.total_seconds()/60:.1f} minutes")
        
        print(f"Downtime Periods: {len(self.stats['downtime_periods'])}")
        
        # Show recent downtime periods
        if self.stats['downtime_periods']:
            print(f"\n🕐 Recent Downtime Periods:")
            for period in self.stats['downtime_periods'][-5:]:  # Last 5
                print(f"  {period['start'].strftime('%m-%d %H:%M')} - {period['end'].strftime('%H:%M')} ({period['duration_minutes']:.1f}m)")
    
    def monitor_loop(self, check_interval=300):
        """Main monitoring loop"""
        logger.info(f"🚀 Bot Monitor Starting - Checking every {check_interval}s")
        logger.info(f"Target: {self.bot_url}")
        
        try:
            while True:
                self.check_bot_health()
                
                # Print stats every 10 checks
                if self.stats['total_checks'] % 10 == 0:
                    self.print_stats()
                
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            logger.info("🛑 Monitoring stopped by user")
            self.print_stats()

def main():
    """Main function"""
    # Configuration - Update these values
    BOT_URL = "https://your-quiz-bot.onrender.com"  # Your bot URL
    TELEGRAM_TOKEN = None  # Optional: Your monitoring bot token for alerts
    ALERT_CHAT_ID = None   # Optional: Chat ID to send alerts to
    
    monitor = BotMonitor(BOT_URL, TELEGRAM_TOKEN, ALERT_CHAT_ID)
    monitor.monitor_loop(check_interval=300)  # Check every 5 minutes

if __name__ == "__main__":
    main()
