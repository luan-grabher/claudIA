from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from core.router import IntentRouter

MAX_TELEGRAM_MESSAGE_LENGTH = 4096


class TelegramChannel:
    def __init__(self, router: IntentRouter, config: dict):
        self.router = router
        self.config = config
        self.telegram_token = config["telegram"]["token"]
        self.allowed_user_ids = set(config["telegram"].get("allowed_user_ids", []))

    async def start(self):
        application = Application.builder().token(self.telegram_token).build()

        application.add_handler(CommandHandler("start", self._handle_start_command))
        application.add_handler(CommandHandler("status", self._handle_status_command))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text_message)
        )
        application.add_handler(
            MessageHandler(filters.PHOTO, self._handle_photo_message)
        )

        print("[ClaudIA] Bot Telegram iniciado. Aguardando mensagens...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    def _sender_is_allowed(self, user_id: int) -> bool:
        if not self.allowed_user_ids:
            return True
        return user_id in self.allowed_user_ids

    async def _handle_start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._sender_is_allowed(update.effective_user.id):
            await update.message.reply_text("Acesso negado.")
            return

        welcome_message = (
            "👋 Olá! Sou a ClaudIA, sua assistente de IA local.\n\n"
            "Posso:\n"
            "• Responder perguntas\n"
            "• Executar comandos no terminal\n"
            "• Ajudar com código\n"
            "• E muito mais\n\n"
            "Pode mandar sua mensagem!"
        )
        await update.message.reply_text(welcome_message)

    async def _handle_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._sender_is_allowed(update.effective_user.id):
            return

        default_model = self.config["models"]["default"]["name"]
        classifier_model = self.config["models"]["classifier"]["name"]

        status_message = (
            f"🤖 *ClaudIA Status*\n\n"
            f"🧠 Modelo principal: `{default_model}`\n"
            f"🔍 Classificador: `{classifier_model}`\n"
            f"✅ Online"
        )
        await update.message.reply_text(status_message, parse_mode="Markdown")

    async def _handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._sender_is_allowed(update.effective_user.id):
            await update.message.reply_text("Acesso negado.")
            return

        user_message = update.message.text
        await update.message.chat.send_action("typing")

        try:
            response = await self.router.route_and_handle_message(user_message)
            await self._send_long_message_in_chunks(update, response)
        except Exception as error:
            print(f"[Telegram] Erro ao processar mensagem: {error}")
            await update.message.reply_text(
                "Ocorreu um erro ao processar sua mensagem. Tente novamente."
            )

    async def _handle_photo_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._sender_is_allowed(update.effective_user.id):
            return

        caption = update.message.caption or "Descreva esta imagem"
        await update.message.chat.send_action("typing")

        try:
            response = await self.router.route_and_handle_message(caption, has_image=True)
            await self._send_long_message_in_chunks(update, response)
        except Exception as error:
            print(f"[Telegram] Erro ao processar foto: {error}")
            await update.message.reply_text("Erro ao processar a imagem.")

    async def _send_long_message_in_chunks(self, update: Update, message: str):
        if len(message) <= MAX_TELEGRAM_MESSAGE_LENGTH:
            await update.message.reply_text(message)
            return

        chunks = [
            message[i:i + MAX_TELEGRAM_MESSAGE_LENGTH]
            for i in range(0, len(message), MAX_TELEGRAM_MESSAGE_LENGTH)
        ]
        for chunk in chunks:
            await update.message.reply_text(chunk)
