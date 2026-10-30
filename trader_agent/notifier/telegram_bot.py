"""Telegram bot (inbound): commands and button presses -> SSoR / control file.

Run:  python -m trader_agent.notifier.telegram_bot

Only your own chat (TELEGRAM_CHAT_ID) is served. Without a chat ID the bot runs
in setup mode and simply tells you your chat ID when you send /start.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ..config import Settings, load_secrets, load_settings
from ..control import Control
from ..ksor import KsorError, load_risk_policy, load_setups
from ..learning import setup_health, weekly_report
from ..news import parse_manual
from ..ssor import SSoR
from ..timeutil import SessionBook, to_display
from .actions import apply_callback, parse_pause, parse_payout
from .messages import (
    format_day_summary,
    format_signal_detail,
    format_status,
    help_text,
    pair_label,
    proposal_buttons,
    tz_label,
)


def control_path(settings: Settings) -> Path:
    return settings.control_path


def _markup(buttons):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    if not buttons:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, callback_data=data) for text, data in row] for row in buttons])


def build_application(token: str, chat_id: str | None, settings: Settings):
    from telegram.ext import Application, CallbackQueryHandler, CommandHandler, filters

    app = Application.builder().token(token).build()

    if not chat_id:
        async def setup_start(update, context):
            await update.message.reply_text(
                f"Aapki chat ID: {update.effective_chat.id}\n"
                "Isay .env mein TELEGRAM_CHAT_ID= ke aage likhein aur bot dobara chalayein."
            )

        app.add_handler(CommandHandler("start", setup_start))
        return app

    owner = int(chat_id)
    only_owner = filters.Chat(chat_id=owner)
    sessions = SessionBook.from_yaml(settings.sessions_path)
    ssor = SSoR(settings.db_path)
    cpath = control_path(settings)
    tz = settings.display_timezone

    def now() -> pd.Timestamp:
        return pd.Timestamp.now(tz="UTC")

    def audit(text: str) -> None:
        ssor.record_reflection(text, "human", now(), tags=("control",))

    def today_bounds():
        day = sessions.trading_day_of(now())
        return day, *sessions.trading_day_bounds(day)

    async def start(update, context):
        await update.message.reply_text("🤖 AI Trader Agent tayyar hai.\n\n" + help_text())

    async def help_cmd(update, context):
        await update.message.reply_text(help_text())

    async def status(update, context):
        control = Control.load(cpath)
        _, start_, end_ = today_bounds()
        summary = ssor.day_summary(start_, end_)
        last = ssor.recent_decisions(1)
        try:
            policy = load_risk_policy(settings.risk_policy_path, sessions.names())
            policy_status, max_losses = policy.status, policy.max_losses_per_day
        except KsorError:
            policy_status, max_losses = "ERROR — check_setup chalayein", "?"
        try:
            approved = len(load_setups(settings.setups_dir))
        except KsorError:
            approved = "ERROR"
        paused = control.paused_until_ts()
        info = {
            "last_seen": to_display(last[0]["at"], tz, "%Y-%m-%d %H:%M") + f" {tz_label(tz)}" if last else None,
            "stopped": control.stopped,
            "paused_until": to_display(paused, tz, "%H:%M") if paused is not None and paused > now() else None,
            "signals": summary["signals"],
            "losses": summary["taken_losses"],
            "max_losses": max_losses,
            "approved_setups": approved,
            "policy_status": policy_status,
            "payouts": control.payouts,
            "news_count": len(control.news),
        }
        await update.message.reply_text(format_status(info))

    async def today(update, context):
        day, start_, end_ = today_bounds()
        await update.message.reply_text(format_day_summary(ssor.day_summary(start_, end_), title=f"Aaj ({day})"))

    async def last(update, context):
        signals = ssor.last_signals(5)
        if not signals:
            await update.message.reply_text("Abhi tak koi signal nahi.")
            return
        lines = []
        for signal in signals:
            outcome = ssor.best_outcome(signal["id"])
            action = ssor.latest_action(signal["id"])
            lines.append(
                f"#{signal['id']} {signal['direction']} {pair_label(signal['pair'])} "
                f"{to_display(signal['signal_time'], tz, '%m-%d %H:%M')} | "
                f"{action['action'] if action else '—'} | {outcome['result'] if outcome else '—'}"
            )
        await update.message.reply_text("\n".join(lines))

    async def why(update, context):
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text("format: /why 12")
            return
        signal_id = int(context.args[0])
        signal = ssor.get_signal(signal_id)
        if signal is None:
            await update.message.reply_text(f"Signal #{signal_id} nahi mila.")
            return
        await update.message.reply_text(
            format_signal_detail(signal, ssor.best_outcome(signal_id), ssor.latest_action(signal_id), tz)
        )

    async def pause(update, context):
        try:
            minutes = parse_pause(context.args)
        except ValueError as exc:
            await update.message.reply_text(f"⚠️ {exc}")
            return
        control = Control.load(cpath)
        control.pause(minutes, now())
        control.save(cpath)
        audit(f"/pause {minutes}")
        until = to_display(control.paused_until_ts(), tz, "%H:%M")
        await update.message.reply_text(f"⏸ {minutes} minute signals band ({until} {tz_label(tz)} tak).")

    async def stop(update, context):
        control = Control.load(cpath)
        control.stopped = True
        control.save(cpath)
        audit("/stop")
        await update.message.reply_text("⛔ Signals band. Dobara shuru karne ke liye /resume.")

    async def resume(update, context):
        control = Control.load(cpath)
        control.resume()
        control.save(cpath)
        audit("/resume")
        await update.message.reply_text("🟢 Signals dobara shuru.")

    async def payout(update, context):
        try:
            pair, value = parse_payout(context.args)
        except ValueError as exc:
            await update.message.reply_text(f"⚠️ {exc}")
            return
        control = Control.load(cpath)
        control.payouts[pair] = value
        control.save(cpath)
        audit(f"/payout {pair} {value}")
        await update.message.reply_text(
            f"💰 {pair_label(pair)} payout {value:.0%} — break-even {1 / (1 + value):.1%}"
        )

    async def news(update, context):
        try:
            event = parse_manual(" ".join(context.args), now().tz_convert(tz).date(), tz)
        except ValueError as exc:
            await update.message.reply_text(f"⚠️ {exc}")
            return
        control = Control.load(cpath)
        control.add_news(event)
        control.save(cpath)
        audit(f"/news {' '.join(context.args)}")
        await update.message.reply_text(
            f"📰 {event.currency} {event.impact} news {to_display(event.time_utc, tz, '%H:%M')} {tz_label(tz)} — "
            "us waqt ke aas paas signals band rahenge (risk policy ke mutabiq)."
        )

    async def on_button(update, context):
        query = update.callback_query
        if update.effective_chat is None or update.effective_chat.id != owner:
            await query.answer()
            return
        await query.answer()
        try:
            text, buttons = apply_callback(ssor, query.data, now())
        except (ValueError, KeyError) as exc:
            await query.message.reply_text(f"⚠️ {exc}")
            return
        await query.edit_message_reply_markup(reply_markup=None)  # no double taps
        await query.message.reply_text(text, reply_markup=_markup(buttons))

    def approved_setups():
        try:
            return load_setups(settings.setups_dir)
        except KsorError:
            return []

    async def setups_cmd(update, context):
        control = Control.load(cpath)
        lines = ["🧩 Setups ki sehat (pichle 50 live signals):"]
        for setup in approved_setups():
            if setup.id in control.paused_setups:
                lines.append(f"⛔ {setup.id}: ruka hua — {control.paused_setups[setup.id]}")
            else:
                payout = control.payouts.get(setup.pairs[0], settings.payout_default)
                lines.append(setup_health(ssor, setup.id, payout, int(settings.learning["drift_window"]),
                                          int(settings.learning["drift_min_trades"])).line())
        if len(lines) == 1:
            lines.append("Koi approved setup nahi.")
        await update.message.reply_text("\n".join(lines))

    async def unpause(update, context):
        setup_id = (context.args[0] if context.args else "").upper()
        control = Control.load(cpath)
        if setup_id not in control.paused_setups:
            await update.message.reply_text(f"{setup_id or '?'} ruka hua nahi hai. Format: /unpause R07")
            return
        control.paused_setups.pop(setup_id)
        control.save(cpath)
        audit(f"/unpause {setup_id}")
        await update.message.reply_text(f"🟢 {setup_id} dobara chalu. Agar phir drift hua to khud ruk jayega.")

    async def proposals(update, context):
        pending = ssor.pending_proposals()
        if not pending:
            await update.message.reply_text("Koi tajweez baqi nahi.")
            return
        for proposal in pending[:5]:
            await update.message.reply_text(
                f"💡 Tajweez #{proposal['id']} ({proposal['sample_size']} trades ka saboot):\n{proposal['pattern']}",
                reply_markup=_markup(proposal_buttons(proposal["id"])),
            )

    async def week(update, context):
        end = now()
        report = weekly_report(ssor, end - pd.Timedelta(days=7), end, settings.payout_default,
                               [s.id for s in approved_setups()])
        await update.message.reply_text(report[:3900])

    commands = {
        "start": start, "help": help_cmd, "status": status, "today": today, "last": last, "why": why,
        "pause": pause, "stop": stop, "resume": resume, "payout": payout, "news": news,
        "setups": setups_cmd, "unpause": unpause, "proposals": proposals, "week": week,
    }
    for name, handler in commands.items():
        app.add_handler(CommandHandler(name, handler, filters=only_owner))
    app.add_handler(CallbackQueryHandler(on_button))
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its INFO lines contain the bot token
    settings = load_settings()
    secrets = load_secrets()
    token = secrets.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN .env mein nahi mila (.env.example dekhein).")
    chat_id = secrets.get("TELEGRAM_CHAT_ID")
    if not chat_id:
        print("Setup mode: Telegram par bot ko /start bhejein — woh aapki chat ID batayega.")
    app = build_application(token, chat_id, settings)
    print("Bot chal raha hai. Band karne ke liye Ctrl+C.")
    app.run_polling()


if __name__ == "__main__":
    main()
