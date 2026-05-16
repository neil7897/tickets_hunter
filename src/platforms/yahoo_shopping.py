#!/usr/bin/env python3
#encoding=utf-8
"""platforms/yahoo_shopping.py -- Yahoo 購物中心 (tw.buy.yahoo.com / buy.yahoo.com.tw)"""

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
    "nodriver_yahoo_shopping_main",
]

_state = {
    "signed_in": False,
    "purchase_done": False,
    "last_button_text": None,
}


async def _is_login_page(tab):
    result = await evaluate_with_pause_check(tab, """
        (function() {
            return window.location.href.includes('login.yahoo.com') ||
                   window.location.href.includes('/login') ||
                   document.querySelector('input[name="username"]') !== null;
        })()
    """)
    return bool(result)


async def _do_login(tab, config_dict):
    debug = util.create_debug_logger(config_dict)
    account = config_dict.get("accounts", {}).get("yahoo_account", "")
    password = config_dict.get("accounts", {}).get("yahoo_password", "")
    if not account or not password:
        debug.log("[YAHOO] 未設定帳號密碼，請手動登入")
        return

    debug.log(f"[YAHOO] 自動登入: {account}")
    await asyncio.sleep(random.uniform(0.5, 1.0))

    await evaluate_with_pause_check(tab, f"""
        (function() {{
            var user = document.querySelector('input[name="username"], input[type="email"], #login-username');
            if (user) {{ user.value = {repr(account)}; user.dispatchEvent(new Event('input', {{bubbles:true}})); }}
        }})()
    """)
    await asyncio.sleep(random.uniform(0.3, 0.5))

    # Yahoo 登入通常分兩步（先帳號後密碼）
    await evaluate_with_pause_check(tab, """
        (function() {
            var btn = document.querySelector('#login-signin, button[type="submit"]');
            if (btn) btn.click();
        })()
    """)
    await asyncio.sleep(random.uniform(1.0, 1.5))

    await evaluate_with_pause_check(tab, f"""
        (function() {{
            var pw = document.querySelector('input[type="password"], #login-passwd');
            if (pw) {{ pw.value = {repr(password)}; pw.dispatchEvent(new Event('input', {{bubbles:true}})); }}
            var btn = document.querySelector('#login-signin, button[type="submit"]');
            if (btn) btn.click();
        }})()
    """)
    debug.log("[YAHOO] 已送出登入")


async def _get_buy_button(tab):
    return await evaluate_with_pause_check(tab, """
        (function() {
            var selectors = [
                '.J-go-buy',
                '.buy-now-btn',
                '#buy-now',
                'button[class*="buy"]',
                'a[class*="buy"]',
                '.btn-buy-now',
            ];
            for (var s of selectors) {
                var el = document.querySelector(s);
                if (el) {
                    return {
                        found: true,
                        disabled: el.disabled || el.classList.contains('disabled') ||
                                  el.classList.contains('out-of-stock') || el.textContent.trim().includes('售完'),
                        text: el.textContent.trim()
                    };
                }
            }
            var allBtns = Array.from(document.querySelectorAll('button, a'));
            var btn = allBtns.find(b =>
                b.textContent.trim().includes('立即購買') || b.textContent.trim().includes('加入購物車')
            );
            if (btn) {
                return {
                    found: true,
                    disabled: btn.disabled || btn.classList.contains('disabled') || btn.classList.contains('out-of-stock'),
                    text: btn.textContent.trim()
                };
            }
            return { found: false, disabled: true, text: '' };
        })()
    """)


async def _click_buy(tab, config_dict):
    debug = util.create_debug_logger(config_dict)
    clicked = await evaluate_with_pause_check(tab, """
        (function() {
            var selectors = ['.J-go-buy', '.buy-now-btn', '#buy-now', 'button[class*="buy"]', '.btn-buy-now'];
            for (var s of selectors) {
                var el = document.querySelector(s);
                if (el && !el.disabled && !el.classList.contains('disabled') && !el.classList.contains('out-of-stock')) {
                    el.click();
                    return el.textContent.trim();
                }
            }
            var btn = Array.from(document.querySelectorAll('button, a')).find(b =>
                (b.textContent.trim().includes('立即購買') || b.textContent.trim().includes('加入購物車')) &&
                !b.disabled && !b.classList.contains('disabled')
            );
            if (btn) { btn.click(); return btn.textContent.trim(); }
            return null;
        })()
    """)
    if clicked:
        debug.log(f"[YAHOO] 已點擊: {clicked}")
        play_sound_while_ordering(config_dict)
        send_discord_notification(config_dict, "ticket", "Yahoo購物")
        send_telegram_notification(config_dict, "ticket", "Yahoo購物")
        return True
    return False


async def nodriver_yahoo_shopping_main(tab, url, config_dict):
    debug = util.create_debug_logger(config_dict)

    if _state["purchase_done"]:
        return

    if await check_and_handle_pause(config_dict):
        return

    if await _is_login_page(tab):
        if not _state["signed_in"]:
            await _do_login(tab, config_dict)
            _state["signed_in"] = True
        return

    # 訂單完成頁
    if '/order/complete' in url or 'thankYou' in url or 'orderComplete' in url:
        if not _state["purchase_done"]:
            debug.log("[YAHOO] 訂單完成！")
            play_sound_while_ordering(config_dict)
            _state["purchase_done"] = True
        return

    # 商品頁
    btn = await _get_buy_button(tab)
    if btn and btn.get("found"):
        text = btn.get("text", "")
        disabled = btn.get("disabled", True)
        if text != _state["last_button_text"]:
            debug.log(f"[YAHOO] 按鈕: {text} (disabled={disabled})")
            _state["last_button_text"] = text
        if not disabled:
            await _click_buy(tab, config_dict)
            await asyncio.sleep(random.uniform(0.3, 0.6))
