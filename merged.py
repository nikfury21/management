#!/usr/bin/env python3
"""
Merged bot: Connect-4 (gravity, 6x7), Tic-Tac-Toe (TTT), Meme fetcher
Framework: python-telegram-bot v20+

Requirements:
    pip install "python-telegram-bot>=20.0" aiohttp

Save as merged_bot.py and run.
"""

import os
import asyncio
import random
import aiohttp
from typing import Dict, List, Optional, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# -------------------- CONFIG --------------------

# Meme subreddits for meme fetcher
MEME_SR = [
    "IndianDankMemes",
    "DesiMeta",
    "IndianMeyMeys",
    "DankIndianMemes",
    "memes",
    "dankmemes",
    "wholesomememes",
]

sent_memes: List[str] = []
MAX_TRACK = 50

PARSE_MODE = ParseMode.HTML

# -------------------- UTIL --------------------
def html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def styled(t: str) -> str:
    # two-style combo: bold + italic + underline would break links; keep <b><i><u>
    return f"<b><i><u>{html_escape(t)}</u></i></b>"

# -------------------- MEME FETCHER (aiohttp) --------------------
async def fetch_meme_api():
    subreddit = random.choice(MEME_SR)
    url = f"https://meme-api.com/gimme/{subreddit}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                meme_url = data.get("url")
                title = data.get("title")
                if not meme_url or meme_url in sent_memes:
                    return None
                sent_memes.append(meme_url)
                if len(sent_memes) > MAX_TRACK:
                    sent_memes.pop(0)
                return {"title": title, "image": meme_url}
        except Exception:
            return None

async def fetch_imgflip():
    url = "https://api.imgflip.com/get_memes"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                memes = data["data"]["memes"]
                meme = random.choice(memes)
                return {"title": meme["name"], "image": meme["url"]}
        except Exception:
            return None

async def get_meme():
    # Try meme-api first several times
    for _ in range(8):
        meme = await fetch_meme_api()
        if meme:
            return meme
    meme = await fetch_imgflip()
    if meme:
        return meme
    return {"title": "No memes right now", "image": "https://i.imgur.com/uV2UoIY.jpeg"}

# -------------------- TIC-TAC-TOE (TTT) --------------------
class TTTGame:
    def __init__(self, starter_id: int, starter_name: str):
        self.board: List[str] = [" "] * 9
        self.player_x: Optional[Tuple[int, str]] = None
        self.player_o: Optional[Tuple[int, str]] = None
        self.starter = (starter_id, starter_name)
        self.turn: str = "X"
        self.started = False
        self.lock = asyncio.Lock()

    def assign_players(self, joiner_id: int, joiner_name: str):
        if random.choice([True, False]):
            self.player_x = self.starter
            self.player_o = (joiner_id, joiner_name)
        else:
            self.player_x = (joiner_id, joiner_name)
            self.player_o = self.starter
        self.turn = "X"
        self.started = True

    def make_move(self, idx: int) -> bool:
        if 0 <= idx < 9 and self.board[idx] == " ":
            self.board[idx] = self.turn
            return True
        return False

    def switch_turn(self):
        self.turn = "O" if self.turn == "X" else "X"

    def check_winner(self) -> Optional[str]:
        b = self.board
        lines = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8),
            (0, 3, 6), (1, 4, 7), (2, 5, 8),
            (0, 4, 8), (2, 4, 6),
        ]
        for a, c, d in lines:
            if b[a] != " " and b[a] == b[c] == b[d]:
                return b[a]
        if all(x != " " for x in b):
            return "DRAW"
        return None

    def render_board(self, disable=False) -> InlineKeyboardMarkup:
        kb = []
        for r in range(3):
            row = []
            for c in range(3):
                i = r * 3 + c
                val = self.board[i]
                # show dot for empty as you requested
                label = "❌" if val == "X" else "⭕️" if val == "O" else "·"
                row.append(InlineKeyboardButton(
                    label,
                    callback_data="ttt_disabled" if disable else f"ttt_move:{i}"
                ))
            kb.append(row)
        return InlineKeyboardMarkup(kb)

    def clickable_name(self, player: Tuple[int, str]) -> str:
        uid, name = player
        return f"<a href='tg://user?id={uid}'>{html_escape(name)}</a>"

    def players_text(self) -> str:
        if not self.started:
            starter_click = self.clickable_name(self.starter)
            return f"<b><i><u>Players:</u></i></b>\n{starter_click}\n<i>Waiting for opponent...</i>"
        px = self.clickable_name(self.player_x)
        po = self.clickable_name(self.player_o)
        return f"<b><i><u>Players:</u></i></b>\nX: {px}\nO: {po}"

def ttt_status_text(game: TTTGame) -> str:
    turn_player = game.player_x if game.turn == "X" else game.player_o
    turn_name = game.clickable_name(turn_player) if turn_player else "?"
    return f"{game.players_text()}\n\n<b><i><u>Turn:</u></i></b> <b>{game.turn}</b> — {turn_name}"

# store TTT games keyed by message_id (so multiple games can run simultaneously in a chat)
TTT_GAMES: Dict[int, TTTGame] = {}

# -------------------- CONNECT-4 (C4) (gravity 6x7) --------------------
C4_EMPTY = "·"
C4_RED = "🔴"
C4_BLUE = "🔵"

# store C4 games keyed by message_id (so multiple games can run simultaneously)
C4_GAMES: Dict[int, dict] = {}

def create_c4_board():
    return [[C4_EMPTY for _ in range(7)] for _ in range(6)]  # 6 rows x 7 cols

def render_c4_markup(board):
    keyboard = []
    for r, row in enumerate(board):
        buttons = [
            InlineKeyboardButton(text=cell, callback_data=f"c4:{r},{c}")
            for c, cell in enumerate(row)
        ]
        keyboard.append(buttons)
    return InlineKeyboardMarkup(keyboard)

def c4_check_winner(board, symbol):
    rows = 6
    cols = 7
    needed = 4
    directions = [(0,1),(1,0),(1,1),(1,-1)]
    for r in range(rows):
        for c in range(cols):
            if board[r][c] != symbol:
                continue
            for dr, dc in directions:
                count = 1
                for k in range(1, needed):
                    nr, nc = r + dr*k, c + dc*k
                    if 0 <= nr < rows and 0 <= nc < cols and board[nr][nc] == symbol:
                        count += 1
                    else:
                        break
                if count >= needed:
                    return True
    return False

# -------------------- HANDLERS: /start and help --------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        styled("Merged Bot: Commands") + "\n\n"
        + "<b><i><u>/meme</u></i></b> - fetch a meme\n"
        + "<b><i><u>/ttt</u></i></b> - start Tic-Tac-Toe\n"
        + "<b><i><u>/ttt_cancel</u></i></b> - cancel a TTT game (reply to game message)\n"
        + "<b><i><u>/c4</u></i></b> - start Connect-4 (gravity)\n",
        parse_mode=PARSE_MODE
    )

# -------------------- MEME COMMAND --------------------
async def meme_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("<b><i><u>Fetching meme...</u></i></b>", parse_mode=PARSE_MODE)
    meme = await get_meme()
    await msg.delete()
    await update.message.reply_photo(meme["image"], caption=f"<b>{html_escape(meme['title'])}</b>", parse_mode=PARSE_MODE)

# -------------------- TTT COMMANDS & CALLBACK --------------------
async def ttt_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # create a game object and send the join message; key by message_id so multiple can exist
    game = TTTGame(user.id, user.full_name)
    join_btn = InlineKeyboardMarkup([[InlineKeyboardButton("Join", callback_data="ttt_join")]])
    sent = await update.message.reply_text(
        styled("New Game Created!") + "\n\n" + game.players_text() + "\n\n" + "<i>Click join to play.</i>",
        parse_mode=PARSE_MODE,
        reply_markup=join_btn
    )
    TTT_GAMES[sent.message_id] = game

async def ttt_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # require that user replies to the game message they want to cancel
    user = update.effective_user
    replied = update.message.reply_to_message
    if not replied:
        await update.message.reply_text(styled("Reply to the game message you want to cancel."), parse_mode=PARSE_MODE)
        return
    msg_id = replied.message_id
    game = TTT_GAMES.get(msg_id)
    if not game:
        await update.message.reply_text(styled("No active TTT game found for that message."), parse_mode=PARSE_MODE)
        return
    if user.id != game.starter[0]:
        await update.message.reply_text(styled("Only the starter can cancel this game."), parse_mode=PARSE_MODE)
        return
    # remove message entry
    TTT_GAMES.pop(msg_id, None)
    # edit the game message to show canceled and remove buttons
    await context.bot.edit_message_text(
        text=styled("Game cancelled."),
        chat_id=replied.chat.id,
        message_id=msg_id,
        parse_mode=PARSE_MODE,
        reply_markup=None
    )

async def ttt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    msg = query.message
    msg_id = msg.message_id
    user = query.from_user

    game = TTT_GAMES.get(msg_id)
    if not game:
        await query.answer("No active game here.", show_alert=True)
        return

    # If join button clicked
    if data == "ttt_join":
        await query.answer()  # answer the callback to clear "loading"
        async with game.lock:
            if game.started:
                await query.message.reply_text(styled("Game already started."), parse_mode=PARSE_MODE)
                return
            if user.id == game.starter[0]:
                await query.message.reply_text(styled("You started this game."), parse_mode=PARSE_MODE)
                return
            game.assign_players(user.id, user.full_name)
            # edit message: start the game and show board
            await query.edit_message_text(
                text=f"{styled('Game Started!')}\n\n{ttt_status_text(game)}",
                parse_mode=PARSE_MODE,
                reply_markup=game.render_board()
            )
            return

    # If move clicked
    if data.startswith("ttt_move:"):
        # If game not started yet
        if not game.started:
            await query.answer("Waiting for a second player.", show_alert=True)
            return
        idx = int(data.split(":")[1])
        expected_id = game.player_x[0] if game.turn == "X" else game.player_o[0]
        if user.id != expected_id:
            await query.answer("!! NOT YOUR TURN !!  Patience, soldier.", show_alert=False)
            return

        async with game.lock:
            ok = game.make_move(idx)
            if not ok:
                await query.answer("Invalid move.", show_alert=True)
                return
            winner = game.check_winner()
            if not winner:
                game.switch_turn()
                await query.edit_message_text(
                    text=f"{styled('Move made!')}\n\n{ttt_status_text(game)}",
                    parse_mode=PARSE_MODE,
                    reply_markup=game.render_board()
                )
                return

            # Game end
            if winner == "DRAW":
                msg_text = f"{styled('Draw!')}\n\n{game.players_text()}"
            else:
                win_name = game.clickable_name(game.player_x if winner == "X" else game.player_o)
                msg_text = (f"{styled('Winner!')}\n\n{game.players_text()}\n\n"
                            f"<b><i><u>Winner:</u></i></b> <b>{winner}</b> — {win_name}")

            # Remove inline buttons (reply_markup=None)
            await query.edit_message_text(text=msg_text, parse_mode=PARSE_MODE, reply_markup=None)
            # delete game state keyed by this message
            TTT_GAMES.pop(msg_id, None)
            return

    # default answer
    await query.answer()

# -------------------- CONNECT-4 HANDLERS --------------------
async def c4_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    game = {
        "board": create_c4_board(),
        "players": [user.id],  # host
        "host": user.id,
        "turn": None,
        "colors": {},          # mapping user_id -> symbol
        "lock": asyncio.Lock(),
    }
    join_kb = InlineKeyboardMarkup([[InlineKeyboardButton("Join Game", callback_data="c4_join")]])
    text = (
        "<b><u>Game Created</u></b>\n\n"
        f"1) <a href='tg://user?id={user.id}'><b><u>{html_escape(user.first_name)}</u></b></a>\n"
        f"2) <i><u>waiting...</u></i>"
    )
    sent = await update.message.reply_text(text, parse_mode=PARSE_MODE, reply_markup=join_kb)
    # key by message id
    C4_GAMES[sent.message_id] = game

async def c4_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    msg = query.message
    msg_id = msg.message_id
    chat_id = msg.chat.id
    user = query.from_user

    game = C4_GAMES.get(msg_id)
    if not game:
        await query.answer("No active game here.", show_alert=True)
        return

    # Handle join
    if data == "c4_join":
        # quick checks
        if user.id in game["players"]:
            await query.answer("You already joined.", show_alert=True)
            return
        if len(game["players"]) >= 2:
            await query.answer("Game already has two players.", show_alert=True)
            return

        async with game["lock"]:
            game["players"].append(user.id)
            # prepare countdown message template (only number will change)
            host_id = game["host"]
            host_chat = await context.bot.get_chat(host_id)
            joined_chat = await context.bot.get_chat(user.id)

            base_text_template = (
                "<b><u>Game Created</u></b>\n\n"
                f"1) <a href='tg://user?id={host_id}'><b><u>{html_escape(host_chat.first_name)}</u></b></a>\n"
                f"2) <a href='tg://user?id={user.id}'><b><u>{html_escape(joined_chat.first_name)}</u></b></a>\n\n"
                "<b><u>Game starting in {n}…</u></b>"
            )

            # edit the same message (use query.edit_message_text)
            await query.edit_message_text(text=base_text_template.format(n=5), parse_mode=PARSE_MODE, reply_markup=None)

            # countdown: replace number only
            for n in range(4, 0, -1):
                await asyncio.sleep(1)
                await query.edit_message_text(text=base_text_template.format(n=n), parse_mode=PARSE_MODE, reply_markup=None)

            await asyncio.sleep(1)

            # assign colors and set turn
            random.shuffle(game["players"])
            game["colors"] = {game["players"][0]: C4_RED, game["players"][1]: C4_BLUE}
            game["turn"] = game["players"][0]

            first = await context.bot.get_chat(game["players"][0])
            second = await context.bot.get_chat(game["players"][1])

            start_text = (
                "<b><u>Game Started</u></b>\n\n"
                f"<a href='tg://user?id={first.id}'><b><u>{html_escape(first.first_name)}</u></b></a> : <i><u>🔴</u></i>\n"
                f"<a href='tg://user?id={second.id}'><b><u>{html_escape(second.first_name)}</u></b></a> : <i><u>🔵</u></i>\n\n"
                f"<b><i>Turn:</i></b> <a href='tg://user?id={game['turn']}'><b><u>{html_escape((await context.bot.get_chat(game['turn'])).first_name)}</u></b></a>"
            )

            await query.edit_message_text(text=start_text, parse_mode=PARSE_MODE, reply_markup=render_c4_markup(game["board"]))
            await query.answer()
            return

    # Handle C4 cell click (data like "c4:r,c")
    if data.startswith("c4:"):
        # ensure user is participant
        if user.id not in game["players"]:
            await query.answer("You are not part of this game.", show_alert=True)
            return

        if game["turn"] != user.id:
            # auto vanish toast
            await query.answer("!! NOT YOUR TURN !!  Patience, soldier.", show_alert=False)
            return

        # parse payload
        try:
            payload = data.split(":", 1)[1]
            _, col_str = payload.split(",")
            col = int(col_str)
        except Exception:
            await query.answer("Invalid cell.", show_alert=True)
            return

        board = game["board"]
        # find bottom-most empty row (gravity)
        drop_row = None
        for r in range(5, -1, -1):
            if board[r][col] == C4_EMPTY:
                drop_row = r
                break
        if drop_row is None:
            await query.answer("Column is full.", show_alert=True)
            return

        # place token
        symbol = game["colors"][user.id]
        board[drop_row][col] = symbol

        # check win
        if c4_check_winner(board, symbol):
            winner_chat = await context.bot.get_chat(user.id)
            win_text = (
                "<b><u>Game Over</u></b>\n\n"
                f"<a href='tg://user?id={winner_chat.id}'><b><u>{html_escape(winner_chat.first_name)}</u></b></a> <b><i>wins!</i></b>"
            )
            # remove buttons
            await query.edit_message_text(text=win_text, parse_mode=PARSE_MODE, reply_markup=None)
            C4_GAMES.pop(msg_id, None)
            await query.answer()
            return

        # check draw
        if all(cell != C4_EMPTY for row in board for cell in row):
            draw_text = "<b><u>Game Over</u></b>\n\n<b><i>Draw</i></b>"
            await query.edit_message_text(text=draw_text, parse_mode=PARSE_MODE, reply_markup=None)
            C4_GAMES.pop(msg_id, None)
            await query.answer()
            return

        # switch turn
        next_player = [p for p in game["players"] if p != user.id][0]
        game["turn"] = next_player
        next_chat = await context.bot.get_chat(next_player)
        status_text = (
            "<b><u>Next Turn</u></b>\n\n"
            f"<b><i>Player:</i></b> <a href='tg://user?id={next_chat.id}'><b><u>{html_escape(next_chat.first_name)}</u></b></a>"
        )
        await query.edit_message_text(text=status_text, parse_mode=PARSE_MODE, reply_markup=render_c4_markup(board))
        await query.answer()
        return

    # default
    await query.answer()


