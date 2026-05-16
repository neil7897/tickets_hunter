#!/usr/bin/env python3
#encoding=utf-8
"""platforms/momo.py -- MOMO 購物網 (momoshop.com.tw)"""

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
    "nodriver_momo_main",
]

_state = {
    "signed_in": False,
    "purchase_done": False,
    "last_button_text": None,
}


async def _is_login_page(tab):
    result = await evaluate_with_pause_check(tab, """
        (function() {
            return document.querySelector('#memId') !== null ||
                   document.querySelector('input[name="memId"]') !== null ||
                   window.location.href.includes('/web/memberLogin');
        })()
    """)
    return bool(result)


async def _do_login(tab, config_dict):
    debug = util.create_debug_logger(config_dict)
    account = config_dict.get("accounts", {}).get("momo_account", "")
    password = config_dict.get("accounts", {}).get("momo_password", "")
    if not account or not password:
        debug.log("[MOMO] 未設定帳號密碼，請手動登入")
        return

    debug.log(f"[MOMO] 自動登入: {account}")
    await asyncio.sleep(random.uniform(0.5, 1.0))

    await evaluate_with_pause_check(tab, f"""
        (function() {{
            var id = document.querySelector('#memId, input[name="memId"]');
            if (id) {{ id.value = {repr(account)}; id.dispatchEvent(new Event('input', {{bubbles:true}})); }}
            var pw = document.querySelector('#passwd, input[name="passwd"], input[type="password"]');
            if (pw) {{ pw.value = {repr(password)}; pw.dispatchEvent(new Event('input', {{bubbles:true}})); }}
        }})()
    """)
    await asyncio.sleep(random.uniform(0.3, 0.5))

    await evaluate_with_pause_check(tab, """
        (function() {
            var btn = document.querySelector('#loginBtn, button[type="submit"]') ||
                      Array.from(document.querySelectorAll('button, input[type="submit"]'))
                          .find(b => (b.textContent || b.value || '').includes('登入'));
            if (btn) btn.click();
        })()
    """)
    debug.log("[MOMO] 已送出登入")


async def _get_buy_button(tab):
    return await evaluate_with_pause_check(tab, """
        (function() {
            var selectors = [
                '.btn-buy',
                '#btn-buy',
                'button[class*="buy"]',
                'a[class*="buy"]',
                '.buyBtn',
                '#buyBtn',
            ];
            for (var s of selectors) {
                var el = document.querySelector(s);
                if (el) {
                    return {
                        found: true,
                        disabled: el.disabled || el.classList.contains('disabled') ||
                                  el.classList.contains('soldout') || el.textContent.trim().includes('售完'),
                        text: el.textContent.trim()
                    };
                }
            }
            // 搜尋包含「立即購買」文字的按鈕
            var allBtns = Array.from(document.querySelectorAll('button, a'));
            var buyBtn = allBtns.find(b => b.textContent.trim().includes('立即購買') || b.textContent.trim().includes('加入購物車'));
            if (buyBtn) {
                return {
                    found: true,
                    disabled: buyBtn.disabled || buyBtn.classList.contains('disabled') || buyBtn.classList.contains('soldout'),
                    text: buyBtn.textContent.trim()
                };
            }
            return { found: false, disabled: true, text: '' };
        })()
    """)


async def _click_buy(tab, config_dict):
    debug = util.create_debug_logger(config_dict)
    clicked = await evaluate_with_pause_check(tab, """
        (function() {
            var selectors = ['.btn-buy', '#btn-buy', 'button[class*="buy"]', '.buyBtn', '#buyBtn'];
            for (var s of selectors) {
                var el = document.querySelector(s);
                if (el && !el.disabled && !el.classList.contains('disabled') && !el.classList.contains('soldout')) {
                    el.click();
                    return el.textContent.trim();
                }
            }
            var allBtns = Array.from(document.querySelectorAll('button, a'));
            var btn = allBtns.find(b =>
                (b.textContent.trim().includes('立即購買') || b.textContent.trim().includes('加入購物車')) &&
                !b.disabled && !b.classList.contains('disabled') && !b.classList.contains('soldout')
            );
            if (btn) { btn.click(); return btn.textContent.trim(); }
            return null;
        })()
    """)
    if clicked:
        debug.log(f"[MOMO] 已點擊: {clicked}")
        play_sound_while_ordering(config_dict)
        send_discord_notification(config_dict, f"[MOMO] 已點擊購買按鈕，請手動完成結帳！")
        send_telegram_notification(config_dict, f"[MOMO] 已點擊購買按鈕，請手動完成結帳！")
        return True
    return False


async def nodriver_momo_main(tab, url, config_dict):
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

    # 訂單確認頁
    if 'orderComplete' in url or 'order/complete' in url or 'thankYou' in url:
        if not _state["purchase_done"]:
            debug.log("[MOMO] 訂單完成！")
            play_sound_while_ordering(config_dict)
            _state["purchase_done"] = True
        return

    # 商品頁：監控購買按鈕
    if 'GD/productDetail' in url or '/goods/' in url or 'goodsDetail' in url:
        btn = await _get_buy_button(tab)
        if btn and btn.get("found"):
            text = btn.get("text", "")
            disabled = btn.get("disabled", True)
            if text != _state["last_button_text"]:
                debug.log(f"[MOMO] 按鈕: {text} (disabled={disabled})")
                _state["last_button_text"] = text
            if not disabled:
                await _click_buy(tab, config_dict)
                await asyncio.sleep(random.uniform(0.3, 0.6))
