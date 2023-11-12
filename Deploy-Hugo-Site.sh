#!/bin/bash

# Clean the public directory
echo "Cleaning public directory..."
rm -rf public

# Build the Hugo site
echo "Building Hugo site..."
hugo

# Ask the user for a commit message
read -p "Enter a commit message: " commit_message

# Deploy to GitHub Pages (replace with your deployment steps)
echo "Deploying to GitHub Pages..."
git add .
git commit -m "$commit_message"
git push origin main

echo "Deployment complete!"
