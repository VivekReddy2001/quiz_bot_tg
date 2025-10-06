#!/usr/bin/env python3
"""
Ultra-Advanced Bot Monitoring System
- Comprehensive health monitoring
- Performance metrics collection
- Automated alerting and escalation
- Historical data analysis
- Multi-bot monitoring support
- Advanced failure prediction
"""
import requests
import time
import json
import logging
import os
import sys
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/bot_monitor.log')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class HealthMetrics:
    timestamp: datetime
    bot_url: str
    status: str
    uptime_seconds: int
    total_requests: int
    successful_polls: int
    errors: int
    active_users: int
    api_calls: int
    rate_limit_hits: int
    recovery_attempts: int
    response_time_ms: float
    memory_usage: int
    persistent_storage: bool

@dataclass
class AlertRule:
    name: str
    condition: str
    threshold: float
    severity: str
    enabled: bool = True

class DatabaseManager:
    """SQLite database for storing monitoring data"""
    
    def __init__(self, db_path: str = '/tmp/bot_monitor.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS health_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    bot_url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    uptime_seconds INTEGER,
                    total_requests INTEGER,
                    successful_polls INTEGER,
                    errors INTEGER,
                    active_users INTEGER,
                    api_calls INTEGER,
                    rate_limit_hits INTEGER,
                    recovery_attempts INTEGER,
                    response_time_ms REAL,
                    memory_usage INTEGER,
                    persistent_storage BOOLEAN
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS downtime_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_url TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    duration_minutes REAL,
                    error_message TEXT,
                    resolved BOOLEAN DEFAULT FALSE
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    bot_url TEXT NOT NULL,
                    rule_name TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    resolved BOOLEAN DEFAULT FALSE
                )
            ''')
            
            conn.commit()
    
    def save_health_metrics(self, metrics: HealthMetrics):
        """Save health metrics to database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO health_metrics 
                (timestamp, bot_url, status, uptime_seconds, total_requests, 
                 successful_polls, errors, active_users, api_calls, rate_limit_hits, 
                 recovery_attempts, response_time_ms, memory_usage, persistent_storage)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                metrics.timestamp.isoformat(),
                metrics.bot_url,
                metrics.status,
                metrics.uptime_seconds,
                metrics.total_requests,
                metrics.successful_polls,
                metrics.errors,
                metrics.active_users,
                metrics.api_calls,
                metrics.rate_limit_hits,
                metrics.recovery_attempts,
                metrics.response_time_ms,
                metrics.memory_usage,
                metrics.persistent_storage
            ))
            conn.commit()
    
    def get_health_history(self, bot_url: str, hours: int = 24) -> List[Dict]:
        """Get health history for a bot"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            cursor = conn.execute('''
                SELECT * FROM health_metrics 
                WHERE bot_url = ? AND timestamp > ?
                ORDER BY timestamp DESC
            ''', (bot_url, cutoff_time.isoformat()))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_downtime_summary(self, bot_url: str, days: int = 7) -> Dict:
        """Get downtime summary for a bot"""
        with sqlite3.connect(self.db_path) as conn:
            cutoff_time = datetime.now() - timedelta(days=days)
            
            cursor = conn.execute('''
                SELECT COUNT(*) as total_events,
                       SUM(duration_minutes) as total_downtime,
                       AVG(duration_minutes) as avg_downtime,
                       MAX(duration_minutes) as max_downtime
                FROM downtime_events 
                WHERE bot_url = ? AND start_time > ?
            ''', (bot_url, cutoff_time.isoformat()))
            
            result = cursor.fetchone()
            return {
                'total_events': result[0] or 0,
                'total_downtime_minutes': result[1] or 0,
                'avg_downtime_minutes': result[2] or 0,
                'max_downtime_minutes': result[3] or 0
            }

class UltraAdvancedBotMonitor:
    """Ultra-advanced bot monitoring system"""
    
    def __init__(self, bot_urls: List[str], telegram_token: str = None, alert_chat_id: str = None):
        self.bot_urls = [url.rstrip('/') for url in bot_urls]
        self.telegram_token = telegram_token
        self.alert_chat_id = alert_chat_id
        
        # Database
        self.db = DatabaseManager()
        
        # HTTP client with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Statistics
        self.stats = {
            'total_checks': 0,
            'successful_checks': 0,
            'failed_checks': 0,
            'start_time': time.time(),
            'last_success': None,
            'last_failure': None,
            'consecutive_failures': 0,
            'performance_metrics': [],
            'alert_count': 0
        }
        
        # Alert rules
        self.alert_rules = [
            AlertRule("High Error Rate", "error_rate", 0.1, "warning"),
            AlertRule("High Response Time", "response_time", 5000, "warning"),
            AlertRule("Bot Down", "status", 0, "critical"),
            AlertRule("High Memory Usage", "memory_usage", 1000, "warning"),
            AlertRule("Rate Limit Issues", "rate_limit_hits", 10, "warning"),
            AlertRule("Recovery Attempts", "recovery_attempts", 5, "info")
        ]
        
        # Configuration
        self.check_interval = 300  # 5 minutes
        self.performance_window = 10  # Check last 10 metrics
        self.alert_cooldown = 1800  # 30 minutes between same alerts
        
        logger.info(f"Ultra-advanced monitor initialized for {len(self.bot_urls)} bots")
    
    def check_bot_health(self, bot_url: str) -> Tuple[bool, Optional[HealthMetrics]]:
        """Check bot health with comprehensive metrics"""
        start_time = time.time()
        
        try:
            response = self.session.get(f"{bot_url}/health", timeout=30)
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            if response.status_code == 200:
                data = response.json()
                
                metrics = HealthMetrics(
                    timestamp=datetime.now(),
                    bot_url=bot_url,
                    status=data.get('status', 'unknown'),
                    uptime_seconds=data.get('uptime_seconds', 0),
                    total_requests=data.get('total_requests', 0),
                    successful_polls=data.get('successful_polls', 0),
                    errors=data.get('errors', 0),
                    active_users=data.get('active_users', 0),
                    api_calls=data.get('api_calls', 0),
                    rate_limit_hits=data.get('rate_limit_hits', 0),
                    recovery_attempts=data.get('recovery_attempts', 0),
                    response_time_ms=response_time,
                    memory_usage=data.get('memory_usage', 0),
                    persistent_storage=data.get('persistent_storage', False)
                )
                
                # Save to database
                self.db.save_health_metrics(metrics)
                
                # Check alert rules
                self.check_alert_rules(metrics)
                
                logger.info(f"✅ {bot_url} - Healthy | Uptime: {metrics.uptime_seconds}s | Response: {response_time:.1f}ms")
                return True, metrics
            else:
                self.handle_failure(bot_url, f"HTTP {response.status_code}")
                return False, None
                
        except requests.exceptions.Timeout:
            self.handle_failure(bot_url, "Timeout")
            return False, None
        except requests.exceptions.ConnectionError:
            self.handle_failure(bot_url, "Connection Error")
            return False, None
        except Exception as e:
            self.handle_failure(bot_url, str(e))
            return False, None
    
    def check_alert_rules(self, metrics: HealthMetrics):
        """Check alert rules and trigger alerts if needed"""
        for rule in self.alert_rules:
            if not rule.enabled:
                continue
                
            should_alert = False
            
            if rule.condition == "error_rate":
                if metrics.total_requests > 0:
                    error_rate = metrics.errors / metrics.total_requests
                    should_alert = error_rate > rule.threshold
                    
            elif rule.condition == "response_time":
                should_alert = metrics.response_time_ms > rule.threshold
                
            elif rule.condition == "status":
                should_alert = metrics.status != "healthy"
                
            elif rule.condition == "memory_usage":
                should_alert = metrics.memory_usage > rule.threshold
                
            elif rule.condition == "rate_limit_hits":
                should_alert = metrics.rate_limit_hits > rule.threshold
                
            elif rule.condition == "recovery_attempts":
                should_alert = metrics.recovery_attempts > rule.threshold
            
            if should_alert:
                self.send_alert(
                    f"🚨 Alert: {rule.name}\n"
                    f"Bot: {metrics.bot_url}\n"
                    f"Value: {self._get_metric_value(metrics, rule.condition)}\n"
                    f"Threshold: {rule.threshold}\n"
                    f"Severity: {rule.severity.upper()}",
                    rule.severity,
                    rule.name
                )
    
    def _get_metric_value(self, metrics: HealthMetrics, condition: str) -> str:
        """Get metric value for alert message"""
        if condition == "error_rate":
            if metrics.total_requests > 0:
                return f"{(metrics.errors / metrics.total_requests) * 100:.1f}%"
            return "0%"
        elif condition == "response_time":
            return f"{metrics.response_time_ms:.1f}ms"
        elif condition == "status":
            return metrics.status
        elif condition == "memory_usage":
            return f"{metrics.memory_usage} items"
        elif condition == "rate_limit_hits":
            return str(metrics.rate_limit_hits)
        elif condition == "recovery_attempts":
            return str(metrics.recovery_attempts)
        return "N/A"
    
    def handle_failure(self, bot_url: str, error: str):
        """Handle bot failure with advanced tracking"""
        self.stats['failed_checks'] += 1
        self.stats['last_failure'] = datetime.now()
        self.stats['consecutive_failures'] += 1
        
        logger.error(f"❌ {bot_url} - Failure: {error}")
        
        # Record downtime event
        self._record_downtime_event(bot_url, error)
    
    def _record_downtime_event(self, bot_url: str, error: str):
        """Record downtime event in database"""
        with sqlite3.connect(self.db.db_path) as conn:
            # Check if there's an unresolved downtime event
            cursor = conn.execute('''
                SELECT id FROM downtime_events 
                WHERE bot_url = ? AND resolved = FALSE
                ORDER BY start_time DESC LIMIT 1
            ''', (bot_url,))
            
            existing_event = cursor.fetchone()
            
            if not existing_event:
                # Create new downtime event
                conn.execute('''
                    INSERT INTO downtime_events (bot_url, start_time, error_message, resolved)
                    VALUES (?, ?, ?, FALSE)
                ''', (bot_url, datetime.now().isoformat(), error))
                conn.commit()
    
    def resolve_downtime_event(self, bot_url: str):
        """Resolve downtime event when bot recovers"""
        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.execute('''
                SELECT id, start_time FROM downtime_events 
                WHERE bot_url = ? AND resolved = FALSE
                ORDER BY start_time DESC LIMIT 1
            ''', (bot_url,))
            
            event = cursor.fetchone()
            
            if event:
                event_id, start_time = event
                duration = (datetime.now() - datetime.fromisoformat(start_time)).total_seconds() / 60
                
                conn.execute('''
                    UPDATE downtime_events 
                    SET end_time = ?, duration_minutes = ?, resolved = TRUE
                    WHERE id = ?
                ''', (datetime.now().isoformat(), duration, event_id))
                conn.commit()
                
                logger.info(f"🟢 {bot_url} - Downtime resolved after {duration:.1f} minutes")
    
    def send_alert(self, message: str, severity: str, rule_name: str = "Unknown"):
        """Send alert via Telegram with cooldown"""
        if not self.telegram_token or not self.alert_chat_id:
            logger.warning(f"🚨 Alert: {message}")
            return
        
        # Check cooldown
        alert_key = f"{rule_name}_{severity}"
        if hasattr(self, '_last_alerts'):
            last_alert = self._last_alerts.get(alert_key)
            if last_alert and time.time() - last_alert < self.alert_cooldown:
                logger.debug(f"Alert {rule_name} in cooldown period")
                return
        else:
            self._last_alerts = {}
        
        self._last_alerts[alert_key] = time.time()
        self.stats['alert_count'] += 1
        
        try:
            emoji_map = {
                "info": "ℹ️",
                "warning": "⚠️",
                "critical": "🚨",
                "success": "✅"
            }
            
            emoji = emoji_map.get(severity, "📢")
            
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = {
                'chat_id': self.alert_chat_id,
                'text': f"{emoji} Bot Monitor Alert\n\n{message}\n\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                'parse_mode': 'HTML'
            }
            
            response = self.session.post(url, json=data, timeout=10)
            if response.status_code == 200:
                logger.info("📱 Alert sent successfully")
            else:
                logger.warning(f"📱 Alert send failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"📱 Alert send error: {e}")
    
    def analyze_performance_trends(self, bot_url: str) -> Dict:
        """Analyze performance trends for a bot"""
        history = self.db.get_health_history(bot_url, hours=24)
        
        if len(history) < 2:
            return {"status": "insufficient_data"}
        
        # Calculate trends
        recent_metrics = history[:self.performance_window]
        older_metrics = history[self.performance_window:self.performance_window*2]
        
        if not older_metrics:
            return {"status": "insufficient_data"}
        
        recent_avg_response = sum(m['response_time_ms'] for m in recent_metrics) / len(recent_metrics)
        older_avg_response = sum(m['response_time_ms'] for m in older_metrics) / len(older_metrics)
        
        recent_error_rate = sum(m['errors'] for m in recent_metrics) / max(sum(m['total_requests'] for m in recent_metrics), 1)
        older_error_rate = sum(m['errors'] for m in older_metrics) / max(sum(m['total_requests'] for m in older_metrics), 1)
        
        return {
            "status": "analyzed",
            "response_time_trend": "improving" if recent_avg_response < older_avg_response else "degrading",
            "error_rate_trend": "improving" if recent_error_rate < older_error_rate else "degrading",
            "recent_avg_response_ms": recent_avg_response,
            "recent_error_rate": recent_error_rate,
            "data_points": len(history)
        }
    
    def generate_comprehensive_report(self, bot_url: str) -> str:
        """Generate comprehensive monitoring report"""
        health_history = self.db.get_health_history(bot_url, hours=24)
        downtime_summary = self.db.get_downtime_summary(bot_url, days=7)
        performance_trends = self.analyze_performance_trends(bot_url)
        
        if not health_history:
            return f"No data available for {bot_url}"
        
        latest_health = health_history[0]
        
        report = f"""
📊 COMPREHENSIVE BOT MONITORING REPORT
{'='*50}
Bot: {bot_url}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📈 CURRENT STATUS
Status: {latest_health['status']}
Uptime: {latest_health['uptime_seconds']}s ({latest_health['uptime_seconds']/3600:.1f}h)
Total Requests: {latest_health['total_requests']:,}
Successful Polls: {latest_health['successful_polls']:,}
Errors: {latest_health['errors']:,}
Active Users: {latest_health['active_users']:,}
API Calls: {latest_health['api_calls']:,}
Rate Limit Hits: {latest_health['rate_limit_hits']:,}
Recovery Attempts: {latest_health['recovery_attempts']:,}
Response Time: {latest_health['response_time_ms']:.1f}ms
Memory Usage: {latest_health['memory_usage']} items
Persistent Storage: {'✅' if latest_health['persistent_storage'] else '❌'}

📊 PERFORMANCE TRENDS (24h)
Data Points: {performance_trends.get('data_points', 0)}
Response Time Trend: {performance_trends.get('response_time_trend', 'unknown')}
Error Rate Trend: {performance_trends.get('error_rate_trend', 'unknown')}
Recent Avg Response: {performance_trends.get('recent_avg_response_ms', 0):.1f}ms
Recent Error Rate: {performance_trends.get('recent_error_rate', 0)*100:.2f}%

🕐 DOWNTIME SUMMARY (7 days)
Total Events: {downtime_summary['total_events']}
Total Downtime: {downtime_summary['total_downtime_minutes']:.1f} minutes
Average Downtime: {downtime_summary['avg_downtime_minutes']:.1f} minutes
Max Downtime: {downtime_summary['max_downtime_minutes']:.1f} minutes

🎯 RECOMMENDATIONS
"""
        
        # Add recommendations based on analysis
        if performance_trends.get('response_time_trend') == 'degrading':
            report += "• Response time is degrading - consider optimization\n"
        
        if performance_trends.get('error_rate_trend') == 'degrading':
            report += "• Error rate is increasing - investigate issues\n"
        
        if latest_health['rate_limit_hits'] > 5:
            report += "• High rate limit hits - implement better throttling\n"
        
        if latest_health['recovery_attempts'] > 3:
            report += "• Multiple recovery attempts - check stability\n"
        
        if not latest_health['persistent_storage']:
            report += "• No persistent storage - data may be lost on restart\n"
        
        if not any(report.endswith(line) for line in ['•']):
            report += "• Bot is performing well! 🎉\n"
        
        return report
    
    def monitor_loop(self):
        """Main monitoring loop with advanced features"""
        logger.info(f"🚀 Ultra-Advanced Bot Monitor Starting")
        logger.info(f"Monitoring {len(self.bot_urls)} bots:")
        for i, url in enumerate(self.bot_urls, 1):
            logger.info(f"  {i}. {url}")
        
        check_cycle = 0
        
        try:
            while True:
                check_cycle += 1
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                logger.info(f"🔍 Monitoring Cycle #{check_cycle} at {current_time}")
                
                # Check all bots
                for bot_url in self.bot_urls:
                    success, metrics = self.check_bot_health(bot_url)
                    
                    if success:
                        self.stats['successful_checks'] += 1
                        self.stats['last_success'] = datetime.now()
                        
                        # Reset consecutive failures
                        if self.stats['consecutive_failures'] > 0:
                            logger.info(f"🔄 {bot_url} - Consecutive failures reset: {self.stats['consecutive_failures']} -> 0")
                            self.stats['consecutive_failures'] = 0
                            self.resolve_downtime_event(bot_url)
                    else:
                        self.stats['failed_checks'] += 1
                        self.stats['consecutive_failures'] += 1
                
                self.stats['total_checks'] += len(self.bot_urls)
                
                # Generate reports every 12 cycles (1 hour)
                if check_cycle % 12 == 0:
                    logger.info("📊 Generating monitoring reports...")
                    for bot_url in self.bot_urls:
                        report = self.generate_comprehensive_report(bot_url)
                        logger.info(f"Report for {bot_url}:\n{report}")
                
                # Sleep before next check
                logger.info(f"😴 Sleeping for {self.check_interval/60:.1f} minutes...")
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            logger.info("🛑 Monitoring stopped by user")
        except Exception as e:
            logger.critical(f"💥 Critical error in monitoring loop: {e}")
        finally:
            logger.info("🛑 Monitoring shutdown complete")

def main():
    """Main function with configuration"""
    # Configuration - Update these values
    BOT_URLS = [
        "https://quiz-bot-tg.onrender.com",  # Your main bot URL
        # Add more bot URLs here if you have multiple instances
    ]
    
    # Optional: Telegram alert configuration
    TELEGRAM_TOKEN = os.environ.get('MONITOR_TELEGRAM_TOKEN')  # Optional
    ALERT_CHAT_ID = os.environ.get('MONITOR_ALERT_CHAT_ID')   # Optional
    
    # Validate configuration
    if not BOT_URLS or not BOT_URLS[0] or BOT_URLS[0] == "https://your-quiz-bot.onrender.com":
        logger.error("❌ Please update BOT_URLS with your actual bot URL!")
        sys.exit(1)
    
    # Create and run monitor
    monitor = UltraAdvancedBotMonitor(BOT_URLS, TELEGRAM_TOKEN, ALERT_CHAT_ID)
    monitor.monitor_loop()

if __name__ == "__main__":
    main()
