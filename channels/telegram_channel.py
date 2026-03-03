import asyncio
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

    def _build_application(self) -> Application:
        app = Application.builder().token(self.telegram_token).build()
        app.add_handler(CommandHandler("start", self._handle_start_command))
        app.add_handler(CommandHandler("status", self._handle_status_command))
        app.add_handler(CommandHandler("setup", self._handle_setup_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text_message))
        app.add_handler(MessageHandler(filters.PHOTO, self._handle_photo_message))
        return app

    async def start(self, send_first_run: bool = False, on_first_run_sent=None):
        if send_first_run:
            app = self._build_application()
            async with app:
                await app.initialize()
                await app.start()
                sent = await self._send_first_run_message(app)
                if sent and on_first_run_sent:
                    on_first_run_sent()
                await app.stop()
                await app.shutdown()

        print("[ClaudIA] Bot Telegram iniciado. Aguardando mensagens...")
        app = self._build_application()
        async with app:
            await app.start()
            await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            await asyncio.Event().wait()
            await app.updater.stop()
            await app.stop()

    async def _send_first_run_message(self, app: Application) -> bool:
        allowed_ids = list(self.allowed_user_ids)
        if not allowed_ids:
            print("[ClaudIA] Nenhum user_id configurado para mensagem de boas-vindas.")
            return False

        first_run_message = (
            "🎉 *ClaudIA iniciada com sucesso!*\n\n"
            "Sua assistente de IA local está online e pronta para uso.\n\n"
            "Use /setup para ver e ajustar as configurações do bot.\n"
            "Use /status para verificar os modelos ativos.\n\n"
            "Pode começar a conversar! 🚀"
        )

        any_sent = False
        for user_id in allowed_ids:
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text=first_run_message,
                    parse_mode="Markdown",
                )
                print(f"[ClaudIA] Mensagem de boas-vindas enviada para {user_id}.")
                any_sent = True
            except Exception as error:
                print(f"[ClaudIA] Não foi possível enviar para {user_id}: {error}")

        return any_sent

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
            "Use /setup para configurar e /status para ver o estado atual.\n"
            "Pode mandar sua mensagem!"
        )
        await update.message.reply_text(welcome_message)

    async def _handle_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._sender_is_allowed(update.effective_user.id):
            return

        default_model = self.config["models"]["default"]["name"]
        classifier_model = self.config["models"]["classifier"]["name"]
        shell_enabled = self.config.get("skills", {}).get("shell", {}).get("enabled", False)

        status_message = (
            f"🤖 *ClaudIA Status*\n\n"
            f"🧠 Modelo principal: `{default_model}`\n"
            f"🔍 Classificador: `{classifier_model}`\n"
            f"🖥️ Shell skill: {'✅ ativa' if shell_enabled else '❌ inativa'}\n"
            f"✅ Online"
        )
        await update.message.reply_text(status_message, parse_mode="Markdown")

    async def _handle_setup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._sender_is_allowed(update.effective_user.id):
            await update.message.reply_text("Acesso negado.")
            return

        default_model = self.config["models"]["default"]["name"]
        classifier_model = self.config["models"]["classifier"]["name"]
        code_model = self.config["models"].get("code", {}).get("name", "(não configurado)")
        vision_model = self.config["models"].get("vision", {}).get("name", "(não configurado)")
        shell_enabled = self.config.get("skills", {}).get("shell", {}).get("enabled", False)
        shell_timeout = self.config.get("skills", {}).get("shell", {}).get("timeout_seconds", 60)
        max_steps = self.config.get("orchestrator", {}).get("max_steps_per_task", 8)
        allowed_ids = list(self.allowed_user_ids)
        ollama_url = self.config.get("ollama", {}).get("base_url", "http://ollama:11434")

        setup_message = (
            "⚙️ *Configuração atual do ClaudIA*\n\n"
            f"*Modelos Ollama:*\n"
            f"  • Classificador: `{classifier_model}`\n"
            f"  • Principal: `{default_model}`\n"
            f"  • Código: `{code_model}`\n"
            f"  • Visão: `{vision_model}`\n\n"
            f"*Ollama URL:* `{ollama_url}`\n\n"
            f"*Skills:*\n"
            f"  • Shell: {'✅ ativa' if shell_enabled else '❌ inativa'} (timeout: {shell_timeout}s)\n\n"
            f"*Orquestrador:* máx {max_steps} passos por tarefa\n\n"
            f"*Usuários autorizados:* `{allowed_ids}`\n\n"
            "Para alterar as configurações, edite o `config.yml` e reinicie o container:\n"
            "`docker compose restart claudia`"
        )
        await update.message.reply_text(setup_message, parse_mode="Markdown")

    async def _handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._sender_is_allowed(update.effective_user.id):
            await update.message.reply_text("Acesso negado.")
            return

        user_message = update.message.text
        await update.message.chat.send_action("typing")

        try:
            response = await self.router.route_and_handle_message(user_message, user_id=update.effective_user.id)
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
            response = await self.router.route_and_handle_message(caption, has_image=True, user_id=update.effective_user.id)
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
