from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def approval_keyboard(approval_id: str):
    return InlineKeyboardMarkup([[InlineKeyboardButton('✅ APPROVE', callback_data=f'apr:a:{approval_id}'), InlineKeyboardButton('❌ REJECT', callback_data=f'apr:r:{approval_id}')]])
