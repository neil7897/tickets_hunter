#!/usr/bin/env python3
#encoding=utf-8
"""platforms/shopee.py -- Shopee 蝦皮購物 (shopee.tw)"""

import asyncio
import random
import time


import util
from nodriver_common import (
    check_and_handle_pause,
    evaluate_with_pause_check,
    play_sound_while_ordering,
    send_discord_notification,
    send_telegram_notification,
    sleep_with_pause_check,
)

__all__ = [
    "nodriver_shopee_main",
]

_state = {
    "signed_in": False,
    "purchase_done": False,
    "last_button_state": None,
    "last_check_time": 0,
}


async def _is_login_page(tab):
    result = await evaluate_with_pause_check(tab, """
        (function() {
            return window.location.href.includes('/buyer/login') ||
                   document.querySelector('input[name="loginKey"]') !== null ||
                   document.querySelector('input[type="password"]') !== null;
        })()
    """)
    return bool(result)


async def _do_login(tab, config_dict):
    debug = util.create_debug_logger(config_dict)
    account = config_dict.get("accounts", {}).get("shopee_account", "")
    password = config_dict.get("accounts", {}).get("shopee_password", "")
    if not account or not password:
        debug.log("[SHOPEE] 未設定帳號密碼，請手動登入")
        return

    debug.log(f"[SHOPEE] 自動登入: {account}")
    await asyncio.sleep(random.uniform(0.5, 1.0))

    await evaluate_with_pause_check(tab, f"""
        (function() {{
            var inputs = document.querySelectorAll('input[type="text"], input[name="loginKey"]');
            if (inputs.length > 0) {{ inputs[0].value = {repr(account)}; inputs[0].dispatchEvent(new Event('input', {{bubbles:true}})); }}
            var pwds = document.querySelectorAll('input[type="password"]');
            if (pwds.length > 0) {{ pwds[0].value = {repr(password)}; pwds[0].dispatchEvent(new Event('input', {{bubbles:true}})); }}
        }})()
    """)
    await asyncio.sleep(random.uniform(0.3, 0.6))

    await evaluate_with_pause_check(tab, """
        (function() {
            var btn = document.querySelector('button[type="submit"]') ||
                      Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('登入'));
            if (btn) btn.click();
        })()
    """)
    debug.log("[SHOPEE] 已送出登入")


async def _get_buy_button_state(tab):
    return await evaluate_with_pause_check(tab, """
        (function() {
            var selectors = [
                'button.btn-solid-primary',
                'button[class*="buy"]',
                'button[class*="purchase"]',
                'button[class*="cart"]',
            ];
            for (var s of selectors) {
                var btn = document.querySelector(s);
                if (btn) {
                    return {
                        found: true,
                        disabled: btn.disabled || btn.classList.contains('disabled') || btn.getAttribute('aria-disabled') === 'true',
                        text: btn.textContent.trim()
                    };
                }
            }
            return { found: false, disabled: true, text: '' };
        })()
    """)


async def _click_buy_button(tab, config_dict):
    debug = util.create_debug_logger(config_dict)
    clicked = await evaluate_with_pause_check(tab, """
        (function() {
            var selectors = [
                'button.btn-solid-primary',
                'button[class*="buy"]',
                'button[class*="purchase"]',
            ];
            for (var s of selectors) {
                var btn = document.querySelector(s);
                if (btn && !btn.disabled) {
                    btn.click();
                    return btn.textContent.trim();
                }
            }
            return null;
        })()
    """)
    if clicked:
        debug.log(f"[SHOPEE] 已點擊購買按鈕: {clicked}")
        return True
    return False


async def _handle_checkout(tab, config_dict):
    debug = util.create_debug_logger(config_dict)
    await asyncio.sleep(random.uniform(1.0, 2.0))

    # 點擊結帳按鈕
    await evaluate_with_pause_check(tab, """
        (function() {
            var btn = Array.from(document.querySelectorAll('button')).find(b =>
                b.textContent.includes('結帳') || b.textContent.includes('Checkout'));
            if (btn && !btn.disabled) btn.click();
        })()
    """)
    debug.log("[SHOPEE] 已點擊結帳，請手動完成付款")
    play_sound_while_ordering(config_dict)
    send_discord_notification(config_dict, "ticket", "Shopee")
    send_telegram_notification(config_dict, "ticket", "Shopee")


async def nodriver_shopee_main(tab, url, config_dict):
    debug = util.create_debug_logger(config_dict)

    if _state["purchase_done"]:
        return

    if await check_and_handle_pause(config_dict):
        return

    now = time.time()
    if now - _state["last_check_time"] < 2.0:
        return
    _state["last_check_time"] = now

    # 登入頁
    if await _is_login_page(tab):
        if not _state["signed_in"]:
            await _do_login(tab, config_dict)
            _state["signed_in"] = True
        return

    # 結帳頁 → 已完成
    if '/checkout' in url or '/order' in url:
        if not _state["purchase_done"]:
            debug.log("[SHOPEE] 進入結帳/訂單頁面，購買流程完成")
            play_sound_while_ordering(config_dict)
            _state["purchase_done"] = True
        return

    # 購物車頁 → 自動結帳
    if '/cart' in url:
        await _handle_checkout(tab, config_dict)
        return

    # 商品頁：監控購買按鈕
    btn_state = await _get_buy_button_state(tab)
    if btn_state and btn_state.get("found"):
        text = btn_state.get("text", "")
        disabled = btn_state.get("disabled", True)
        if text != _state["last_button_state"]:
            debug.log(f"[SHOPEE] 按鈕狀態: {text} (disabled={disabled})")
            _state["last_button_state"] = text

        if not disabled:
            success = await _click_buy_button(tab, config_dict)
            if success:
                await asyncio.sleep(random.uniform(0.3, 0.6))
