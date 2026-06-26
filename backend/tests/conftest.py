import os

# Set environment variables for testing before other modules are imported
os.environ["AI_PROVIDER"] = "local"
os.environ["DLP_PROVIDER"] = "local"
os.environ["STORAGE_PROVIDER"] = "local"
os.environ["CITI_LOGO_PATH"] = ""
# Keep image generation offline in tests: with no worker configured the image
# service returns a mock placeholder instead of calling the Cloudflare worker.
os.environ["CLOUDFLARE_IMAGE_WORKER_URL"] = ""
os.environ["CLOUDFLARE_IMAGE_WORKER_API_KEY"] = ""
# No stock-photo key in tests -> stock source disabled, AI fallback used (mock).
os.environ["STOCK_PHOTOS_API_KEY"] = ""
# High rate limits so tests don't hit 429 under CI parallelism
os.environ["RATE_LIMIT_GENERATE"] = "10000/minute"
os.environ["RATE_LIMIT_EXPORT"] = "10000/minute"
os.environ["RATE_LIMIT_UPLOADS"] = "10000/minute"
