import asyncio
import logging
from firebase_admin import firestore
import config

logger = logging.getLogger(__name__)

async def get_user_settings(user_id: int) -> dict:
    """Fetches user settings from Firestore."""
    db = config.get_firestore_db()
    app_id = config.get_app_id()
    if not db:
        logger.error("Firestore DB not available.")
        return {}
    
    # Construct the user-specific collection path
    user_settings_collection_path = config.USERS_COLLECTION.format(app_id=app_id, userId=str(user_id))
    doc_ref = db.collection(user_settings_collection_path).document(str(user_id)).collection("settings").document("night_mode")
    
    try:
        doc = await asyncio.to_thread(doc_ref.get)
        return doc.to_dict() if doc.exists else {}
    except Exception as e:
        logger.error(f"Error fetching settings for user {user_id}: {e}")
        return {}

async def update_user_settings(user_id: int, settings: dict):
    """Updates user settings in Firestore."""
    db = config.get_firestore_db()
    app_id = config.get_app_id()
    if not db:
        logger.error("Firestore DB not available. Cannot update settings.")
        return
    
    user_settings_collection_path = config.USERS_COLLECTION.format(app_id=app_id, userId=str(user_id))
    doc_ref = db.collection(user_settings_collection_path).document(str(user_id)).collection("settings").document("night_mode")
    
    try:
        await asyncio.to_thread(doc_ref.set, settings, merge=True)
        logger.info(f"Updated settings for user {user_id}: {settings}")
    except Exception as e:
        logger.error(f"Error updating settings for user {user_id}: {e}")

async def add_scheduled_media(user_id: int, chat_id: int, message_id: int, media_file_id: str, media_type: str, schedule_time: str) -> str:
    """Adds a scheduled media entry to Firestore and returns its ID."""
    db = config.get_firestore_db()
    app_id = config.get_app_id()
    if not db:
        logger.error("Firestore DB not available. Cannot add scheduled media.")
        return ""
    
    user_scheduled_media_collection_path = config.USERS_COLLECTION.format(app_id=app_id, userId=str(user_id))
    collection_ref = db.collection(user_scheduled_media_collection_path).document(str(user_id)).collection("scheduled_media")
    
    try:
        doc_ref = await asyncio.to_thread(collection_ref.add, {
            "chat_id": chat_id,
            "message_id": message_id,
            "media_file_id": media_file_id,
            "media_type": media_type,
            "schedule_time": schedule_time, # HH:MM string (UTC)
            "user_id": user_id, # Store user_id explicitly for easier querying
            "created_at": firestore.SERVER_TIMESTAMP
        })
        logger.info(f"Added scheduled media for user {user_id}: {doc_ref.id}")
        return doc_ref.id
    except Exception as e:
        logger.error(f"Error adding scheduled media for user {user_id}: {e}")
        return ""

async def get_all_scheduled_media(user_id: int) -> list[dict]:
    """Fetches all scheduled media for a specific user."""
    db = config.get_firestore_db()
    app_id = config.get_app_id()
    if not db:
        logger.error("Firestore DB not available.")
        return []

    user_scheduled_media_collection_path = config.USERS_COLLECTION.format(app_id=app_id, userId=str(user_id))
    collection_ref = db.collection(user_scheduled_media_collection_path).document(str(user_id)).collection("scheduled_media")
    
    try:
        docs = await asyncio.to_thread(collection_ref.get)
        return [{**doc.to_dict(), "id": doc.id} for doc in docs]
    except Exception as e:
        logger.error(f"Error fetching scheduled media for user {user_id}: {e}")
        return []

async def delete_scheduled_media(user_id: int, media_id: str):
    """Deletes a scheduled media entry from Firestore."""
    db = config.get_firestore_db()
    app_id = config.get_app_id()
    if not db:
        logger.error("Firestore DB not available. Cannot delete scheduled media.")
        return
    
    user_scheduled_media_collection_path = config.USERS_COLLECTION.format(app_id=app_id, userId=str(user_id))
    doc_ref = db.collection(user_scheduled_media_collection_path).document(str(user_id)).collection("scheduled_media").document(media_id)
    
    try:
        await asyncio.to_thread(doc_ref.delete)
        logger.info(f"Deleted scheduled media {media_id} for user {user_id}")
    except Exception as e:
        logger.error(f"Error deleting scheduled media {media_id} for user {user_id}: {e}")

