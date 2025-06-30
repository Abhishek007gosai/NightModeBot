import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from apscheduler.schedulers.asyncio import AsyncIOScheduler # Import scheduler

import db_manager
from jobs import delete_message_job, send_scheduled_media_job
from utils import get_media_file_id, send_media_by_type

logger = logging.getLogger(__name__)

# Get APScheduler instance for job management
scheduler = AsyncIOScheduler() # This should ideally be passed in from main or accessed globally (carefully)

# --- FSM States for Bot Interaction ---
class NightModeStates(StatesGroup):
    waiting_for_delete_duration = State()
    waiting_for_scheduled_media = State()
    waiting_for_schedule_time = State() # Not strictly used with current flow, but kept for future expansion


def register_handlers(dp: Dispatcher, bot: Bot):
    """Registers all command and message handlers to the dispatcher."""
    # Command handlers
    dp.message.register(command_start_handler, Command("start"))
    dp.message.register(command_help_handler, Command("help"))
    dp.message.register(set_delete_timer_command, Command("set_delete_timer"))
    dp.message.register(cancel_delete_timer_command, Command("cancel_delete_timer"))
    dp.message.register(schedule_media_command, Command("schedule_media"))
    dp.message.register(cancel_schedule_command_no_arg, Command("cancel_schedule")) # For just /cancel_schedule
    dp.message.register(process_cancel_schedule_id, lambda message: message.text.startswith('/cancel_schedule ') and len(message.text.split()) > 1) # For /cancel_schedule <ID>

    # Media handlers (for auto-deletion and scheduling)
    dp.message.register(handle_media_for_deletion, NightModeStates.waiting_for_delete_duration,
                        content_types=[types.ContentType.STICKER, types.ContentType.ANIMATION, types.ContentType.PHOTO, types.ContentType.VIDEO])
    dp.message.register(handle_scheduled_media, NightModeStates.waiting_for_scheduled_media,
                        content_types=[types.ContentType.STICKER, types.ContentType.ANIMATION, types.ContentType.PHOTO, types.ContentType.VIDEO])

    # Pass bot to jobs via partial if necessary, or ensure jobs can access it
    # For APScheduler jobs, they will receive `bot` as an argument because it's passed in main.py
    # and in load_and_reschedule_media.


# --- Command Handlers ---
@dp.message(Command("start"))
async def command_start_handler(message: Message, state: FSMContext) -> None:
    """Handles the /start command."""
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    await message.answer(
        f"Hello, {username}! 👋\n\n"
        "I'm your Night Mode Bot for Telegram media.\n\n"
        "Here's what I can do:\n"
        "🌙 **Automatic Media Deletion (Night Mode)**\n"
        "  - Use `/set_delete_timer <minutes>` to have stickers, GIFs, photos, and videos automatically deleted after the set time.\n"
        "  - Example: `/set_delete_timer 5` (deletes media after 5 minutes).\n"
        "  - Use `/cancel_delete_timer` to stop automatic deletion.\n\n"
        "⏰ **Scheduled Media Sending**\n"
        "  - Use `/schedule_media <HH:MM>` to schedule a sticker, GIF, photo, or video to be sent daily at a specific time.\n"
        "  - Example: `/schedule_media 08:00` (sends media daily at 8 AM UTC).\n"
        "  - Use `/cancel_schedule` to view and cancel your scheduled media.\n\n"
        "Type /help for more information."
    )
    # Store user_id in Firestore if it's the first time
    await db_manager.update_user_settings(user_id, {"last_active": firestore.SERVER_TIMESTAMP})
    # Display the user ID
    await message.answer(f"Your User ID for this app is: `{user_id}` (for private data storage)", parse_mode=ParseMode.MARKDOWN_V2)


@dp.message(Command("help"))
async def command_help_handler(message: Message) -> None:
    """Handles the /help command."""
    await message.answer(
        "Here's how to use me:\n\n"
        "🌙 **Automatic Media Deletion:**\n"
        "  - `/set_delete_timer <minutes>`: Start auto-deletion. After this, any *new* media you send (sticker, GIF, photo, video) in *this chat* will be deleted after `<minutes>`. The bot needs to be an admin in groups with 'delete messages' permission.\n"
        "  - `/cancel_delete_timer`: Stop auto-deletion.\n\n"
        "⏰ **Scheduled Media Sending:**\n"
        "  - `/schedule_media <HH:MM>`: Prepare to schedule media. After this, send the media you want to schedule.\n"
        "  - `/cancel_schedule`: List your scheduled media and cancel them by ID.\n\n"
        "**Important Notes:**\n"
        "- All times are in **UTC** for scheduling.\n"
        "- For auto-deletion in groups, I need to be an admin with **'Delete Messages'** permission.\n"
        "- I only handle stickers, GIFs, photos, and videos for now.\n"
    )

@dp.message(Command("set_delete_timer"))
async def set_delete_timer_command(message: Message, state: FSMContext):
    """Handles /set_delete_timer command."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Usage: `/set_delete_timer <minutes>` (e.g., `/set_delete_timer 5`)\n"
                            "This will delete any new stickers, GIFs, photos, or videos you send after 5 minutes.")
        return

    try:
        duration_minutes = int(args[1])
        if duration_minutes <= 0:
            await message.reply("Please provide a positive number of minutes.")
            return

        user_id = message.from_user.id
        # Store duration in user settings
        settings = await db_manager.get_user_settings(user_id)
        settings['delete_timer_minutes'] = duration_minutes
        settings['delete_timer_active_chat_id'] = message.chat.id # Store which chat it's active for
        await db_manager.update_user_settings(user_id, settings)

        await state.set_state(NightModeStates.waiting_for_delete_duration)
        await message.reply(f"Okay! I will delete stickers, GIFs, photos, and videos sent in this chat automatically after "
                            f"{duration_minutes} minute(s).\n"
                            "Now, send me the media you want to be automatically deleted, or type `/cancel_delete_timer` to stop.")
    except ValueError:
        await message.reply("Invalid number. Please provide a whole number for minutes (e.g., `/set_delete_timer 10`).")

@dp.message(Command("cancel_delete_timer"))
async def cancel_delete_timer_command(message: Message, state: FSMContext):
    """Handles /cancel_delete_timer command."""
    user_id = message.from_user.id
    settings = await db_manager.get_user_settings(user_id)
    if 'delete_timer_minutes' in settings:
        del settings['delete_timer_minutes']
        if 'delete_timer_active_chat_id' in settings:
            del settings['delete_timer_active_chat_id']
        await db_manager.update_user_settings(user_id, settings)
        await state.clear()
        await message.reply("Automatic media deletion has been cancelled.")
    else:
        await message.reply("No active automatic media deletion timer set.")

@dp.message(NightModeStates.waiting_for_delete_duration, content_types=[types.ContentType.STICKER, types.ContentType.ANIMATION, types.ContentType.PHOTO, types.ContentType.VIDEO])
async def handle_media_for_deletion(message: Message, state: FSMContext):
    """Handles media messages when a delete timer is active."""
    user_id = message.from_user.id
    settings = await db_manager.get_user_settings(user_id)

    delete_timer_minutes = settings.get('delete_timer_minutes')
    active_chat_id = settings.get('delete_timer_active_chat_id')

    if delete_timer_minutes is None or active_chat_id != message.chat.id:
        # This state might have been left hanging or command was for another chat
        await message.reply("No active auto-deletion timer for this chat. Use `/set_delete_timer <minutes>` first.")
        await state.clear()
        return

    # Schedule the deletion
    run_at = datetime.now() + timedelta(minutes=delete_timer_minutes)
    scheduler.add_job(
        delete_message_job,
        'date',
        run_date=run_at,
        args=[message.bot, message.chat.id, message.message_id], # Pass bot instance to job
        id=f"delete_msg_{message.chat.id}_{message.message_id}_{datetime.now().timestamp()}"
    )
    logger.info(f"Scheduled deletion for message {message.message_id} in chat {message.chat.id} at {run_at} UTC.")
    await message.reply(f"This media will be deleted automatically in {delete_timer_minutes} minute(s).")
    # Don't clear state, allow continuous auto-deletion until cancelled

@dp.message(Command("schedule_media"))
async def schedule_media_command(message: Message, state: FSMContext):
    """Handles /schedule_media command."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Usage: `/schedule_media <HH:MM>` (e.g., `/schedule_media 09:30`)\n"
                            "This will send the next media you send daily at 09:30 UTC.")
        return

    time_str = args[1]
    try:
        # Validate time format
        scheduled_time = datetime.strptime(time_str, "%H:%M").time()
        # Store time in state
        await state.update_data(schedule_time_str=time_str)
        await state.set_state(NightModeStates.waiting_for_scheduled_media)
        await message.reply(f"Okay! I will schedule media to be sent daily at {time_str} UTC.\n"
                            "Now, send me the sticker, GIF, photo, or video you want to schedule.")
    except ValueError:
        await message.reply("Invalid time format. Please use HH:MM (e.g., `09:30`).")

@dp.message(NightModeStates.waiting_for_scheduled_media, content_types=[types.ContentType.STICKER, types.ContentType.ANIMATION, types.ContentType.PHOTO, types.ContentType.VIDEO])
async def handle_scheduled_media(message: Message, state: FSMContext):
    """Handles media message after /schedule_media command."""
    data = await state.get_data()
    schedule_time_str = data.get("schedule_time_str")

    if not schedule_time_str:
        await message.reply("Something went wrong. Please start again with `/schedule_media <HH:MM>`.")
        await state.clear()
        return

    media_file_id, media_type = await get_media_file_id(message)

    if not media_file_id:
        await message.reply("I can only schedule stickers, GIFs, photos, or videos. Please send one of these types.")
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    # Save to Firestore
    scheduled_id = await db_manager.add_scheduled_media(user_id, chat_id, message.message_id, media_file_id, media_type, schedule_time_str)

    if scheduled_id:
        # Add job to scheduler
        hour, minute = map(int, schedule_time_str.split(':'))
        # Using a fixed ID for the job based on scheduled_id ensures uniqueness
        # and allows `replace_existing=True` to re-register on bot restart.
        scheduler.add_job(
            send_scheduled_media_job,
            'cron',
            hour=hour,
            minute=minute,
            second=0,
            timezone='UTC',
            args=[message.bot, user_id, chat_id, media_file_id, media_type, scheduled_id], # Pass bot instance to job
            id=f"send_sch_{scheduled_id}",
            replace_existing=True
        )
        await message.reply(
            f"Media scheduled successfully! It will be sent daily at **{schedule_time_str} UTC**.\n"
            f"Scheduled ID: `{scheduled_id}`\n"
            "You can cancel it with `/cancel_schedule`."
        )
    else:
        await message.reply("Failed to schedule media due to a database error. Please try again.")

    await state.clear()

@dp.message(Command("cancel_schedule"))
async def cancel_schedule_command_no_arg(message: Message):
    """Handles /cancel_schedule command without arguments (to list schedules)."""
    user_id = message.from_user.id
    scheduled_items = await db_manager.get_all_scheduled_media(user_id)

    if not scheduled_items:
        await message.reply("You have no scheduled media.")
        return

    response_text = "Your scheduled media:\n\n"
    for item in scheduled_items:
        response_text += (
            f"ID: `{item['id']}`\n"
            f"Type: `{item['media_type'].capitalize()}`\n"
            f"Time: `{item['schedule_time']} UTC`\n"
            f"Chat ID: `{item['chat_id']}`\n"
            f"To cancel, use `/cancel_schedule {item['id']}`.\n\n"
        )
    await message.reply(response_text, parse_mode=types.ParseMode.MARKDOWN)

async def process_cancel_schedule_id(message: Message):
    """Handles the ID argument for /cancel_schedule."""
    args = message.text.split(maxsplit=1)
    schedule_id_to_cancel = args[1]
    user_id = message.from_user.id
    
    # Verify the user actually owns this scheduled ID
    scheduled_items = await db_manager.get_all_scheduled_media(user_id)
    found = False
    for item in scheduled_items:
        if item['id'] == schedule_id_to_cancel:
            found = True
            break
    
    if not found:
        await message.reply(f"No scheduled media found with ID: `{schedule_id_to_cancel}` for your user. Please check the ID and try again.")
        return

    try:
        await db_manager.delete_scheduled_media(user_id, schedule_id_to_cancel)
        # Remove job from scheduler
        job_id = f"send_sch_{schedule_id_to_cancel}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info(f"Removed APScheduler job {job_id}")
        await message.reply(f"Scheduled media with ID `{schedule_id_to_cancel}` has been cancelled and removed.")
    except Exception as e:
        logger.error(f"Error cancelling scheduled media {schedule_id_to_cancel}: {e}")
        await message.reply(f"Failed to cancel scheduled media. Error: {e}")

