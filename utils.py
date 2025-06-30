import logging
from aiogram.types import Message, PhotoSize
from aiogram import Bot

logger = logging.getLogger(__name__)

async def get_media_file_id(message: Message):
    """Extracts file_id and media type from a message."""
    if message.sticker:
        return message.sticker.file_id, "sticker"
    elif message.animation:
        return message.animation.file_id, "gif"
    elif message.photo:
        # Get the largest photo size
        largest_photo: PhotoSize = message.photo[-1]
        return largest_photo.file_id, "photo"
    elif message.video:
        return message.video.file_id, "video"
    else:
        return None, None

async def send_media_by_type(chat_id: int, media_file_id: str, media_type: str, bot_instance: Bot):
    """Sends media based on its type."""
    try:
        if media_type == "sticker":
            await bot_instance.send_sticker(chat_id, media_file_id)
        elif media_type == "gif":
            await bot_instance.send_animation(chat_id, media_file_id)
        elif media_type == "photo":
            await bot_instance.send_photo(chat_id, media_file_id)
        elif media_type == "video":
            await bot_instance.send_video(chat_id, media_file_id)
        else:
            logger.warning(f"Unknown media type for sending: {media_type}")
            return False
        return True
    except Exception as e:
        logger.error(f"Error sending media (type: {media_type}, file_id: {media_file_id}) to chat {chat_id}: {e}")
        return False

