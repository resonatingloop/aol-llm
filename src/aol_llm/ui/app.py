"""Textual app shell for AOL-LLM."""

from collections.abc import AsyncIterator

from textual.app import App
from textual.widgets import ListView

from aol_llm.chat import ChatEvent, ChatService, ModelChoice
from aol_llm.core.errors import ProviderError
from aol_llm.core.types import Buddy, Conversation
from aol_llm.export import export_last_pair_markdown, export_markdown
from aol_llm.ui.commands import SlashCommand, parse_slash_command
from aol_llm.ui.modals import (
    BuddyPickerModal,
    ConfirmModal,
    ExportFormatModal,
    ModelPickerModal,
    RenameModal,
    SystemPromptModal,
)
from aol_llm.ui.screens import MainScreen, SettingsScreen
from aol_llm.ui.styles import APP_BINDINGS, APP_CSS
from aol_llm.ui.widgets import (
    BuddyList,
    ChatTranscript,
    Composer,
    ConversationList,
    StatusBar,
)


class THRESHOLD36(App[None]):
    TITLE = "THRESHOLD36"
    CSS = APP_CSS
    BINDINGS = APP_BINDINGS

    def __init__(self, chat_service: ChatService | None = None) -> None:
        super().__init__()
        self._chat_service = chat_service or ChatService()
        self._current_buddy: Buddy | None = None
        self._buddy_ids: list[str] = []
        self._current_conversation: Conversation | None = None
        self._conversation_ids: list[str] = []
        self._sending = False

    async def on_mount(self) -> None:
        await self.push_screen(MainScreen())
        self._chat_service.init()
        buddy = self._chat_service.default_buddy()
        self._refresh_buddy_list()
        self._set_current_buddy(buddy)

    def action_new_conversation(self) -> None:
        buddy = self._current_buddy or self._chat_service.default_buddy()
        conversation = self._chat_service.create_conversation_for_buddy(buddy.id)
        self._refresh_conversation_list()
        self._set_current_conversation(conversation)

    async def action_send_message(self) -> None:
        if self._sending or self._current_conversation is None:
            return

        composer = self.screen.query_one(Composer)
        content = composer.text().strip()
        if not content:
            return
        command = parse_slash_command(content)
        if command is not None:
            composer.clear()
            self._handle_slash_command(command)
            return

        self._sending = True
        composer.clear()
        transcript = self.screen.query_one(ChatTranscript)
        transcript.append_message("user", content)

        try:
            await self._stream_assistant_response(
                self._chat_service.send_message(
                    self._current_conversation.id,
                    content,
                ),
                show_provider_error=True,
            )
        except ProviderError as error:
            self.notify(str(error), severity="error")
        finally:
            self._sending = False
            self._refresh_conversation_list()

    def action_rename_current_chat(self) -> None:
        if self._current_conversation is None:
            return
        self.push_screen(
            RenameModal(self._current_conversation.title),
            self._rename_current_chat,
        )

    def action_rename_current_buddy(self) -> None:
        if self._current_buddy is None:
            return
        self.push_screen(
            RenameModal(self._current_buddy.screen_name, "Rename buddy"),
            self._rename_current_buddy,
        )

    def action_edit_system_prompt(self) -> None:
        if self._current_conversation is None:
            return
        self.push_screen(
            SystemPromptModal(self._current_conversation.system_prompt),
            self._update_system_prompt,
        )

    def action_open_model_picker(self) -> None:
        self.push_screen(
            ModelPickerModal(self._chat_service.model_choices()),
            self._switch_current_model,
        )

    def action_open_buddy_picker(self) -> None:
        self.push_screen(
            BuddyPickerModal(self._chat_service.list_buddies()),
            self._switch_current_buddy,
        )

    def action_open_settings(self) -> None:
        if isinstance(self.screen, SettingsScreen):
            self.pop_screen()
            return
        if self._current_conversation is None:
            return
        self.push_screen(
            SettingsScreen(
                self._current_conversation.assistant_name,
                self._default_reply_name(),
            ),
            self._update_settings,
        )

    async def action_retry_last(self) -> None:
        if self._sending or self._current_conversation is None:
            return

        self._sending = True
        try:
            self._chat_service.prepare_retry(self._current_conversation.id)
            self._load_current_transcript()
            await self._stream_assistant_response(
                self._chat_service.stream_response(self._current_conversation.id)
            )
        except (ProviderError, ValueError) as error:
            self.notify(str(error), severity="error")
            self._load_current_transcript()
        finally:
            self._sending = False
            self._refresh_conversation_list()

    def action_export_current_chat(self) -> None:
        self.push_screen(ExportFormatModal(), self._export_current_chat)

    def action_copy_current_chat(self) -> None:
        if self._current_conversation is None:
            return
        messages = self._chat_service.messages(self._current_conversation.id)
        self.copy_to_clipboard(
            export_markdown(
                self._current_conversation,
                messages,
                reply_name=self._reply_name(),
            )
        )
        self.notify("Copied chat to clipboard")

    def action_copy_last_pair(self) -> None:
        if self._current_conversation is None:
            return
        messages = self._chat_service.messages(self._current_conversation.id)
        content = export_last_pair_markdown(messages, reply_name=self._reply_name())
        if content is None:
            self.notify("No complete prompt/response pair to copy", severity="warning")
            return
        self.copy_to_clipboard(content)
        self.notify("Copied last prompt/response pair")

    def action_archive_current_chat(self) -> None:
        self.push_screen(
            ConfirmModal("Archive current chat?"),
            self._archive_current_chat,
        )

    def action_delete_current_chat(self) -> None:
        self.push_screen(
            ConfirmModal("Delete current chat?"), self._delete_current_chat
        )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "buddy-list":
            if event.index >= len(self._buddy_ids):
                return
            self._set_current_buddy(
                self._chat_service.get_buddy(self._buddy_ids[event.index])
            )
            return

        if event.list_view.id != "conversation-list":
            return
        if event.index >= len(self._conversation_ids):
            return

        conversation = self._chat_service.get_conversation(
            self._conversation_ids[event.index]
        )
        self._set_current_conversation(conversation)

    def _rename_current_chat(self, title: str | None) -> None:
        if self._current_conversation is None or title is None:
            return
        try:
            self._current_conversation = self._chat_service.rename_conversation(
                self._current_conversation.id,
                title,
            )
        except ValueError as error:
            self.notify(str(error), severity="error")
            return
        self._refresh_conversation_list()

    def _rename_current_buddy(self, name: str | None) -> None:
        if self._current_buddy is None or name is None:
            return
        try:
            self._current_buddy = self._chat_service.rename_buddy(
                self._current_buddy.id,
                name,
            )
        except ValueError as error:
            self.notify(str(error), severity="error")
            return
        self._refresh_buddy_list()
        self._refresh_status_model()

    def _switch_current_model(self, choice: ModelChoice | None) -> None:
        if self._current_conversation is None or choice is None:
            return
        conversation = self._chat_service.switch_model(
            self._current_conversation.id,
            choice.provider_id,
            choice.model,
        )
        self._set_current_conversation(conversation)
        self._refresh_buddy_list()
        self._refresh_conversation_list()

    def _switch_current_buddy(self, buddy: Buddy | None) -> None:
        if buddy is None:
            return
        self._set_current_buddy(buddy)

    def _update_system_prompt(self, system_prompt: str | None) -> None:
        if self._current_conversation is None or system_prompt is None:
            return
        self._current_conversation = self._chat_service.update_system_prompt(
            self._current_conversation.id,
            system_prompt,
        )
        self.notify("a-way updated")

    def _update_settings(self, reply_name: str | None) -> None:
        if self._current_conversation is None or reply_name is None:
            return
        self._current_conversation = self._chat_service.update_conversation_reply_name(
            self._current_conversation.id,
            reply_name,
        )
        self._load_current_transcript()
        self.notify("Reply name updated")

    def _handle_slash_command(self, command: SlashCommand) -> None:
        if command.name == "cache":
            self._handle_cache_command(command.args)
            return
        if command.name == "help":
            self.notify(
                "Commands: /cache, /copy, /export, /away, /buddy, "
                "/chatname, /settings, /quit"
            )
            return
        if command.args:
            self.notify(f"Usage: /{command.name}", severity="warning")
            return
        if command.name == "copy":
            self.action_copy_last_pair()
            return
        if command.name == "export":
            self.action_export_current_chat()
            return
        if command.name == "away":
            self.action_edit_system_prompt()
            return
        if command.name == "buddy":
            self.action_open_buddy_picker()
            return
        if command.name == "chatname":
            self.action_rename_current_chat()
            return
        if command.name == "quit":
            self.exit()
            return
        if command.name == "settings":
            self.action_open_settings()
            return
        label = "/" if not command.name else f"/{command.name}"
        self.notify(f"Unknown command: {label}", severity="warning")

    def _handle_cache_command(self, args: tuple[str, ...]) -> None:
        if len(args) > 1:
            self.notify("Usage: /cache on|1h|5m|off|status", severity="warning")
            return

        subcommand = args[0].lower() if args else "status"
        if subcommand == "on":
            self._chat_service.set_prompt_cache_mode("1h")
            self.notify("Claude prompt cache 1h")
            return
        if subcommand == "1h":
            self._chat_service.set_prompt_cache_mode("1h")
            self.notify("Claude prompt cache 1h")
            return
        if subcommand == "5m":
            self._chat_service.set_prompt_cache_mode("5m")
            self.notify("Claude prompt cache 5m")
            return
        if subcommand == "off":
            self._chat_service.set_prompt_cache_mode("off")
            self.notify("Claude prompt cache off")
            return
        if subcommand == "status":
            self.notify(
                f"Claude prompt cache is {self._chat_service.prompt_cache_mode()}"
            )
            return
        self.notify("Usage: /cache on|1h|5m|off|status", severity="warning")

    def _export_current_chat(self, format: str | None) -> None:
        if self._current_conversation is None or format is None:
            return
        path = self._chat_service.export_conversation(
            self._current_conversation.id,
            format,
        )
        self.notify(f"Exported {path}")

    def _archive_current_chat(self, confirmed: bool | None) -> None:
        if self._current_conversation is None or not confirmed:
            return
        self._chat_service.archive_conversation(self._current_conversation.id)
        self._refresh_conversation_list()
        self._set_current_conversation_for_current_buddy()

    def _delete_current_chat(self, confirmed: bool | None) -> None:
        if self._current_conversation is None or not confirmed:
            return
        self._chat_service.delete_conversation(self._current_conversation.id)
        self._refresh_conversation_list()
        self._set_current_conversation_for_current_buddy()

    def _refresh_buddy_list(self) -> None:
        buddies = self._chat_service.list_buddies()
        self._buddy_ids = [buddy.id for buddy in buddies]
        self.screen.query_one(BuddyList).set_buddies(buddies)

    def _refresh_conversation_list(self) -> None:
        if self._current_buddy is None:
            conversations: list[Conversation] = []
        else:
            conversations = self._chat_service.list_conversations_for_buddy(
                self._current_buddy.id
            )
        self._conversation_ids = [conversation.id for conversation in conversations]
        self.screen.query_one(ConversationList).set_conversations(conversations)

    def _set_current_buddy(self, buddy: Buddy) -> None:
        self._current_buddy = buddy
        self._refresh_conversation_list()
        self._set_current_conversation_for_current_buddy()

    def _set_current_conversation_for_current_buddy(self) -> None:
        if self._current_buddy is None:
            return
        self._set_current_conversation(
            self._chat_service.ensure_conversation_for_buddy(self._current_buddy.id)
        )
        self._refresh_conversation_list()

    def _set_current_conversation(self, conversation: Conversation) -> None:
        self._current_conversation = conversation
        if conversation.buddy_id is not None and conversation.buddy_id != getattr(
            self._current_buddy,
            "id",
            None,
        ):
            self._current_buddy = self._chat_service.get_buddy(conversation.buddy_id)
        self._refresh_status_model()
        self._load_current_transcript()

    def _refresh_status_model(self) -> None:
        if self._current_conversation is None:
            return
        prefix = (
            f"{self._current_buddy.screen_name} / "
            if self._current_buddy is not None
            else ""
        )
        self.screen.query_one(StatusBar).set_model(
            f"{prefix}{self._current_conversation.provider_id}",
            self._current_conversation.model,
        )

    def _load_current_transcript(self) -> None:
        if self._current_conversation is None:
            return
        transcript = self.screen.query_one(ChatTranscript)
        transcript.clear_messages()
        messages = self._chat_service.messages(self._current_conversation.id)
        for message in messages:
            transcript.append_message(
                message.role,
                message.content,
                self._display_name(message.role),
            )
        self.screen.query_one(StatusBar).set_usage(
            sum(message.input_tokens or 0 for message in messages),
            sum(message.output_tokens or 0 for message in messages),
            sum(message.cost_usd or 0.0 for message in messages),
        )

    async def _stream_assistant_response(
        self,
        events: AsyncIterator[ChatEvent],
        *,
        show_provider_error: bool = False,
    ) -> None:
        transcript = self.screen.query_one(ChatTranscript)
        assistant_message = transcript.append_message(
            "assistant",
            "",
            self._reply_name(),
        )
        assistant_text = ""
        try:
            async for event in events:
                if not event.done:
                    assistant_text += event.text
                    assistant_message.update(f"{self._reply_name()}: {assistant_text}")
                    transcript.scroll_to_end()
                    continue
                self.screen.query_one(StatusBar).add_usage(
                    event.input_tokens,
                    event.output_tokens,
                    event.cost_usd,
                    event.cache_read_input_tokens,
                    event.cache_creation_5m_input_tokens,
                    event.cache_creation_1h_input_tokens,
                )
        except ProviderError as error:
            if show_provider_error:
                assistant_message.update(f"{self._reply_name()}: {error}")
            raise

    def _display_name(self, role: str) -> str:
        if role == "assistant":
            return self._reply_name()
        return role

    def _reply_name(self) -> str:
        if self._current_conversation is None:
            return "assistant"
        return self._chat_service.conversation_reply_name(self._current_conversation.id)

    def _default_reply_name(self) -> str:
        if self._current_buddy is not None:
            return self._current_buddy.screen_name or self._current_buddy.name
        return "assistant"


def run() -> None:
    THRESHOLD36().run()
