import asyncio
import logging
import json
import os

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Firebase imports
import firebase_admin
from firebase_admin import credentials, firestore

# Local imports
import config
from db_manager import get_all_scheduled_media, get_user_settings, update_user_settings
from handlers import register_handlers
from jobs import send_scheduled_media_job
from utils import get_media_file_id, send_media_by_type

logger = logging.getLogger(__name__)

async def initialize_firebase_and_db():
    """Initializes Firebase and returns the Firestore client."""
    try:
        # Use environment variables provided by Canvas or fallback for local dev
        app_id = os.getenv('__app_id', config.DEFAULT_APP_ID)
        firebase_config_str = os.getenv('__firebase_config', '{}')

        if not firebase_config_str or firebase_config_str == '{}':
            logger.error("FIREBASE_CONFIG environment variable is not set or is empty.")
            logger.info("Falling back to anonymous sign-in or no-op database operations.")
            return None, app_id

        firebase_config = json.loads(firebase_config_str)
        cred = credentials.Certificate(firebase_config)
        
        # Check if app is already initialized to prevent errors on hot reload/re-initialization
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
            logger.info("Firebase app initialized.")
        else:
            logger.info("Firebase app already initialized.")

        db = firestore.client()
        logger.info("Firestore client obtained.")
        return db, app_id
    except Exception as e:
        logger.error(f"Error during Firebase initialization: {e}")
        return None, config.DEFAULT_APP_ID


async def load_and_reschedule_media(bot_instance: Bot, scheduler_instance: AsyncIOScheduler, firestore_db):
    """Loads all scheduled media from Firestore and re-adds them to the scheduler on startup."""
    if not firestore_db:
        logger.warning("Firestore database not initialized. Cannot load scheduled media.")
        return

    logger.info("Loading and rescheduling all existing media...")
    
    # In a real multi-user scenario, this might involve more complex iteration
    # or a dedicated collection for all scheduled jobs if performance is critical.
    # For now, we iterate through all known users' scheduled_media subcollections.
    
    # Note: This is a simplified approach. If you have millions of users,
    # you'd need a more optimized way to query all scheduled items across subcollections.
    # A Collection Group Query could be used, but requires indexes.
    
    # We will assume that `get_all_scheduled_media` can effectively retrieve across users
    # by iterating through user IDs that exist in the `USERS_COLLECTION`
    # Or for a single-user bot, simply query the user's collection.

    total_jobs_rescheduled = 0
    # This is a placeholder for fetching user IDs. In a real app, you might have a
    # master list of user IDs or iterate through users collection.
    # For this simplified example, we'll try to guess user IDs or assume they are known.
    # A robust solution might use a dedicated 'all_scheduled_jobs' collection at the root.
    
    # As the bot runs, users interact, and their IDs get into Firestore implicitly.
    # For loading, we need to find existing user documents.
    try:
        users_ref = firestore_db.collection(config.USERS_COLLECTION.format(app_id='*')) # Use wildcard if no specific app_id known at this stage
        # This wildcard approach doesn't work directly with Firebase `collection` method.
        # Instead, we need to use a Collection Group Query if `scheduled_media` is a subcollection
        # under different user IDs.
        
        # A more direct (but potentially less efficient for many users) way is to get all
        # user documents and then their subcollections.
        
        user_docs_stream = firestore_db.collection_group("scheduled_media").stream()
        
        # Iterate through scheduled media directly using a collection group query
        for doc in user_docs_stream:
            item = doc.to_dict()
            try:
                user_id_str = doc.reference.parent.parent.id # Get user ID from path: users/{user_id}/scheduled_media/{doc_id}
                user_id = int(user_id_str)

                # Ensure all required fields are present
                if all(k in item for k in ['chat_id', 'media_file_id', 'media_type', 'schedule_time']):
                    hour, minute = map(int, item['schedule_time'].split(':'))
                    trigger = CronTrigger(hour=hour, minute=minute, second=0, timezone='UTC')
                    scheduler_instance.add_job(
                        send_scheduled_media_job,
                        trigger,
                        args=[bot_instance, user_id, item['chat_id'], item['media_file_id'], item['media_type'], doc.id],
                        id=f"send_sch_{doc.id}",
                        replace_existing=True # Important for re-scheduling on startup
                    )
                    logger.info(f"Rescheduled job {doc.id} for user {user_id} at {item['schedule_time']} UTC.")
                    total_jobs_rescheduled += 1
                else:
                    logger.warning(f"Skipping incomplete scheduled media document: {doc.id}")

            except ValueError:
                logger.error(f"Invalid user ID or time format in scheduled media document: {doc.id}")
            except Exception as e:
                logger.error(f"Error rescheduling job {doc.id}: {e}")
        
    except Exception as e:
        logger.error(f"Error loading scheduled media for rescheduling: {e}")

    logger.info(f"Finished rescheduling {total_jobs_rescheduled} jobs.")


async def main() -> None:
    """Main function to start the bot."""
    config.setup_logging()
    
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in config.py or environment variables. Exiting.")
        return

    # Initialize Firebase and Firestore DB
    firestore_db, app_id_from_env = await initialize_firebase_and_db()
    # Pass db and app_id to config and handlers
    config.set_firestore_instance(firestore_db, app_id_from_env)
    
    bot = Bot(token=config.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()

    # Register all handlers from handlers.py
    register_handlers(dp, bot)

    # Start the scheduler
    scheduler = AsyncIOScheduler()
    scheduler.start()
    logger.info("APScheduler started.")

    # Load and reschedule existing jobs from Firestore
    # This needs access to the bot and the Firestore instance.
    await load_and_reschedule_media(bot, scheduler, firestore_db)

    # Start polling for updates
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        scheduler.shutdown()
        logger.info("Bot session closed and scheduler shut down.")

if __name__ == "__main__":
    asyncio.run(main())

