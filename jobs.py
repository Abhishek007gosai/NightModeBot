import logging
from aiogram import Bot
import utils
import db_manager # To delete from db if needed after sending/failure

logger = logging.getLogger(__name__)

async def delete_message_job(bot: Bot, chat_id: int, message_id: int):
    """Job to delete a specific message."""
    try:
        await bot.delete_message(chat_id, message_id)
        logger.info(f"Deleted message {message_id} in chat {chat_id}")
    except Exception as e:
        logger.error(f"Failed to delete message {message_id} in chat {chat_id}: {e}")

async def send_scheduled_media_job(bot: Bot, user_id: int, chat_id: int, media_file_id: str, media_type: str, schedule_id: str):
    """Job to send scheduled media."""
    success = await utils.send_media_by_type(chat_id, media_file_id, media_type)
    if success:
        logger.info(f"Sent scheduled media {schedule_id} to chat {chat_id}")
    else:
        logger.error(f"Failed to send scheduled media {schedule_id} to chat {chat_id}")
        # Optionally, you might want to log this failure or notify the user
        # or even retry, depending on your bot's logic.
      
