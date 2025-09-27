#!/bin/bash

# Quiz Bot Deployment Script for Render
# This script helps you deploy your bot quickly

echo "🚀 Quiz Bot Deployment Helper"
echo "=============================="

# Check if git is initialized
if [ ! -d ".git" ]; then
    echo "❌ Git not initialized. Run 'git init' first."
    exit 1
fi

# Check for required files
required_files=("app.py" "requirements.txt" "render.yaml" "Procfile")
for file in "${required_files[@]}"; do
    if [ ! -f "$file" ]; then
        echo "❌ Missing required file: $file"
        exit 1
    fi
done

echo "✅ All required files present"

# Check if bot token is set in environment
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "⚠️  Warning: TELEGRAM_BOT_TOKEN not set in environment"
    echo "   Remember to set it in Render dashboard"
fi

# Add and commit changes
echo "📝 Committing changes..."
git add .
git status

read -p "Enter commit message (or press Enter for default): " commit_msg
if [ -z "$commit_msg" ]; then
    commit_msg="Update bot for deployment"
fi

git commit -m "$commit_msg"

# Check if remote is set
if ! git remote get-url origin > /dev/null 2>&1; then
    echo "❌ No git remote set. Please add your GitHub repository:"
    echo "   git remote add origin https://github.com/yourusername/quiz_bot_tg.git"
    exit 1
fi

# Push to GitHub
echo "🔄 Pushing to GitHub..."
git push origin main || git push origin master

echo ""
echo "✅ Code pushed to GitHub successfully!"
echo ""
echo "🎯 Next Steps:"
echo "1. Go to https://render.com"
echo "2. Create new Web Service from your GitHub repo"
echo "3. Set environment variables:"
echo "   - TELEGRAM_BOT_TOKEN: your_bot_token"
echo "   - WEBHOOK_URL: https://your-app-name.onrender.com/your_bot_token"
echo "4. Deploy and visit /set_webhook"
echo ""
echo "📚 For detailed instructions, see DEPLOYMENT_GUIDE.md"
echo "🛌 For sleep handling, see RENDER_SLEEP_SOLUTION.md"
