import os
import logging

# --- Bot Configuration ---
# Use os.getenv to get environment variables.
# For local development, you can set these in a .env file and use python-dotenv.
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Default values for Firebase and App ID, useful for local testing
DEFAULT_APP_ID = 'default-night-mode-bot'
FIREBASE_CONFIG_PLACEHOLDER = '{}'

# --- Firebase Global Instances (will be set dynamically) ---
_firestore_db_instance = None
_app_id_instance = None

def set_firestore_instance(db_instance, app_id_val):
    """Sets the global Firestore DB instance and app ID."""
    global _firestore_db_instance, _app_id_instance
    _firestore_db_instance = db_instance
    _app_id_instance = app_id_val
    logging.info(f"Firestore instance and app ID '{app_id_val}' set in config.")

def get_firestore_db():
    """Returns the global Firestore DB instance."""
    if _firestore_db_instance is None:
        logging.warning("Firestore DB instance not yet initialized.")
    return _firestore_db_instance

def get_app_id():
    """Returns the global app ID."""
    if _app_id_instance is None:
        logging.warning("App ID instance not yet initialized.")
    return _app_id_instance

# --- Firestore Collection Paths ---
# Use format strings for app_id and user_id, which will be filled at runtime.
# Public data (not extensively used in this bot, but for completeness)
PUBLIC_COLLECTION = "artifacts/{app_id}/public"
# Private user data
USERS_COLLECTION = "artifacts/{app_id}/users"


# --- Logging Configuration ---
def setup_logging():
    """Configures basic logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logging.getLogger('httpx').setLevel(logging.WARNING) # Suppress verbose http client logs
    logging.getLogger('asyncio').setLevel(logging.WARNING) # Suppress verbose asyncio logs
    logging.getLogger('APScheduler').setLevel(logging.INFO) # Keep APScheduler info
    logging.info("Logging configured.")

