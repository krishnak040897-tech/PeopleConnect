import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'peopleconnect-premium-secure-key-2026-production')
    
    # Database Configuration
    # Render automatically provides the DATABASE_URL environment variable
    DATABASE_URL = os.environ.get("DATABASE_URL")
    
    # Upload folder is kept for temporary processing if needed, 
    # but permanent storage is now Cloudinary.
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'temp_uploads')
    DEBUG = False # Set to False for production
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    
    # Razorpay Integration Credentials
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', 'rzp_test_dhYJFlohg88eyl')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', 'dummy_secret_for_validation')

    # Ensure temp upload folder exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)