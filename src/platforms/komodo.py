#!/usr/bin/env python3
#encoding=utf-8
"""platforms/komodo.py -- KOMODO Station (komodostation.com)"""

import asyncio
import random

import util
from nodriver_common import (
    check_and_handle_pause,
    evaluate_with_pause_check,
    play_sound_while_ordering,
    send_discord_notification,
    send_telegram_notification,
)

__all__ = [
    "nodriver_komodo_main",
]

_state = {
    "signed_in": False,
    "purchase_done": False,
    "last_button_text": None,
    "clicked": False,
}


async def _is_login_page(tab):
    result = await evaluate_with_pause_check(tab, """
        (function() {
            return window.location.href.includes('/login') ||
                   window.location.href.includes('/signin') ||
                   document.querySelector('input[type="email"]') !== null ||
                   document.querySelector('form[class*="login"]') !== null;
        })()
    """)
    return bool(result)


async def _do_login(tab, config_dict):
    debug = util.create_debug_logger(config_dict)
    account = config_dict.get("accounts", {}).get("komodo_account", "")
    password = config_dict.get("accounts", {}).get("komodo_password", "")
    if not account or not password:
        debug.log("[KOMODO] 未設定帳號密碼，請手動登入")
        return

    debug.log(f"[KOMODO] 自動登入: {account}")
    await asyncio.sleep(random.uniform(0.5, 1.0))

    await evaluate_with_pause_check(tab, f"""
        (function() {{
            var email = document.querySelector('input[type="email"], input[name="email"]');
            if (email) {{ email.value = {repr(account)}; email.dispatchEvent(new Event('input', {{bubbles:true}})); }}
            var pw = document.querySelector('input[type="password"]');
            if (pw) {{ pw.value = {repr(password)}; pw.dispatchEvent(new Event('input', {{bubbles:true}})); }}
        }})()
    """)
    await asyncio.sleep(random.uniform(0.3, 0.5))

    await evaluate_with_pause_check(tab, """
        (function() {
            var btn = document.querySelector('button[type="submit"]') ||
                      Array.from(document.querySelectorAll('button')).find(b =>
                          b.textContent.includes('登入') || b.textContent.includes('Login') || b.textContent.includes('Sign In')
                      );
            if (btn) btn.click();
        })()
    """)
    debug.log("[KOMODO] 已送出登入")


async def _get_buy_button(tab):
    """偵測 KOMODO 商品頁的購買/加入購物車按鈕狀態。
    售罄時按鈕通常為 disabled 或有 soldout class；開賣後變為可點擊。"""
    return await evaluate_with_pause_check(tab, """
        (function() {
            // KOMODO 常見購買按鈕選擇器
            var selectors = [
                'button[class*="add-to-cart"]',
                'button[class*="addToCart"]',
                'button[class*="buy"]',
                '.btn-add-cart',
                '.add-to-cart-btn',
                '#add-to-cart',
            ];
            for (var s of selectors) {
                var el = document.querySelector(s);
                if (el) {
                    var soldOut = el.disabled ||
                                  el.classList.contains('disabled') ||
                                  el.classList.contains('soldout') ||
                                  el.classList.contains('sold-out') ||
                                  el.textContent.trim().includes('售罄') ||
                                  el.textContent.trim().includes('Sold Out') ||
                                  el.textContent.trim().includes('售完');
                    return { found: true, disabled: soldOut, text: el.textContent.trim() };
                }
            }
            // 廣泛搜尋包含購買相關文字的按鈕
            var allBtns = Array.from(document.querySelectorAll('button'));
            var buyBtn = allBtns.find(b => {
                var t = b.textContent.trim();
                return t.includes('加入購物車') || t.includes('立即購買') ||
                       t.includes('Add to Cart') || t.includes('Buy Now') ||
                       t.includes('售罄') || t.includes('Sold Out');
            });
            if (buyBtn) {
                var t = buyBtn.textContent.trim();
                var soldOut = buyBtn.disabled ||
                              buyBtn.classList.contains('disabled') ||
                              t.includes('售罄') || t.includes('Sold Out') || t.includes('售完');
                return { found: true, disabled: soldOut, text: t };
            }
            return { found: false, disabled: true, text: '' };
        })()
    """)


async def _click_buy(tab, config_dict):
    debug = util.create_debug_logger(config_dict)
    clicked = await evaluate_with_pause_check(tab, """
        (function() {
            var selectors = [
                'button[class*="add-to-cart"]',
                'button[class*="addToCart"]',
                'button[class*="buy"]',
                '.btn-add-cart',
                '.add-to-cart-btn',
                '#add-to-cart',
            ];
            for (var s of selectors) {
                var el = document.querySelector(s);
                if (el && !el.disabled && !el.classList.contains('disabled') &&
                    !el.classList.contains('soldout') && !el.classList.contains('sold-out') &&
                    !el.textContent.includes('售罄') && !el.textContent.includes('Sold Out')) {
                    el.click();
                    return el.textContent.trim();
                }
            }
            var btn = Array.from(document.querySelectorAll('button')).find(b => {
                var t = b.textContent.trim();
                return (t.includes('加入購物車') || t.includes('立即購買') || t.includes('Add to Cart')) &&
                       !b.disabled && !b.classList.contains('disabled') &&
                       !t.includes('售罄') && !t.includes('Sold Out');
            });
            if (btn) { btn.click(); return btn.textContent.trim(); }
            return null;
        })()
    """)
    if clicked:
        debug.log(f"[KOMODO] 已點擊: {clicked}")
        play_sound_while_ordering(config_dict)
        send_discord_notification(config_dict, "ticket", "KOMODO")
        send_telegram_notification(config_dict, "ticket", "KOMODO")
        return True
    return False


async def _handle_cart(tab, config_dict):
    """在購物車頁自動點擊結帳。"""
    debug = util.create_debug_logger(config_dict)
    await asyncio.sleep(random.uniform(0.8, 1.2))
    clicked = await evaluate_with_pause_check(tab, """
        (function() {
            var btn = Array.from(document.querySelectorAll('button, a')).find(b =>
                b.textContent.trim().includes('結帳') || b.textContent.trim().includes('Checkout')
            );
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        })()
    """)
    if clicked:
        debug.log("[KOMODO] 已點擊結帳")


async def nodriver_komodo_main(tab, url, config_dict):
    debug = util.create_debug_logger(config_dict)

    if _state["purchase_done"]:
        return

    if await check_and_handle_pause(config_dict):
        return

    # 登入頁
    if await _is_login_page(tab):
        if not _state["signed_in"]:
            await _do_login(tab, config_dict)
            _state["signed_in"] = True
        return

    # 訂單完成頁
    if '/order' in url and ('complete' in url or 'success' in url or 'thank' in url.lower()):
        if not _state["purchase_done"]:
            debug.log("[KOMODO] 訂單完成！")
            play_sound_while_ordering(config_dict)
            _state["purchase_done"] = True
        return

    # 購物車頁
    if '/cart' in url:
        if not _state["clicked"]:
            await _handle_cart(tab, config_dict)
        return

    # 商品頁：監控按鈕從「售罄」→「加入購物車」
    btn = await _get_buy_button(tab)
    if btn and btn.get("found"):
        text = btn.get("text", "")
        disabled = btn.get("disabled", True)

        if text != _state["last_button_text"]:
            debug.log(f"[KOMODO] 按鈕狀態變更: 「{_state['last_button_text']}」→「{text}」(disabled={disabled})")
            _state["last_button_text"] = text

        if not disabled and not _state["clicked"]:
            success = await _click_buy(tab, config_dict)
            if success:
                _state["clicked"] = True
                await asyncio.sleep(random.uniform(0.3, 0.6))
    else:
        if _state["last_button_text"] is not None:
            debug.log("[KOMODO] 找不到購買按鈕，等待頁面載入...")
            _state["last_button_text"] = None
