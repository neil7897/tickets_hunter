#!/usr/bin/env python3
#encoding=utf-8
"""platforms/pchome.py -- PChome 24h 購物 (24h.pchome.com.tw)"""

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
)

__all__ = [
    "nodriver_pchome_main",
]

_state = {
    "signed_in": False,
    "purchase_done": False,
    "last_button_text": None,
    "clicked": False,
    "cart_handled": False,
    "checkout_handled": False,
    "last_check_time": 0,
}


async def _is_login_page(tab):
    result = await evaluate_with_pause_check(tab, """
        (function() {
            var url = window.location.href;
            return url.includes('ecvip.pchome.com.tw/login') ||
                   url.includes('member.pchome.com.tw') ||
                   document.querySelector('#loginId') !== null ||
                   document.querySelector('input[name="loginId"]') !== null;
        })()
    """)
    return bool(result)


async def _do_login(tab, config_dict):
    debug = util.create_debug_logger(config_dict)
    account = config_dict.get("accounts", {}).get("pchome_account", "")
    password = config_dict.get("accounts", {}).get("pchome_password", "")
    if not account or not password:
        debug.log("[PCHOME] 未設定帳號密碼，請手動登入")
        return

    debug.log(f"[PCHOME] 自動登入: {account}")
    await asyncio.sleep(random.uniform(1.0, 1.5))

    # 填帳號
    filled = await evaluate_with_pause_check(tab, f"""
        (function() {{
            var id = document.querySelector('#loginId, input[name="loginId"], input[type="email"], input[type="text"]');
            if (id) {{
                id.focus();
                id.value = {repr(account)};
                id.dispatchEvent(new Event('input', {{bubbles:true}}));
                id.dispatchEvent(new Event('change', {{bubbles:true}}));
                return true;
            }}
            return false;
        }})()
    """)
    debug.log(f"[PCHOME] 帳號填入: {filled}")
    await asyncio.sleep(random.uniform(0.5, 0.8))

    # 填密碼
    await evaluate_with_pause_check(tab, f"""
        (function() {{
            var pw = document.querySelector('#loginPwd, input[name="loginPwd"], input[type="password"]');
            if (pw) {{
                pw.focus();
                pw.value = {repr(password)};
                pw.dispatchEvent(new Event('input', {{bubbles:true}}));
                pw.dispatchEvent(new Event('change', {{bubbles:true}}));
            }}
        }})()
    """)
    await asyncio.sleep(random.uniform(0.5, 0.8))

    # 點登入按鈕
    await evaluate_with_pause_check(tab, """
        (function() {
            var btn = document.querySelector('#loginSubmit, button[type="submit"]') ||
                      Array.from(document.querySelectorAll('button, input[type="submit"]'))
                          .find(b => (b.textContent || b.value || '').includes('登入'));
            if (btn) { btn.click(); return true; }
            return false;
        })()
    """)
    debug.log("[PCHOME] 已送出登入")


async def _get_buy_button(tab):
    return await evaluate_with_pause_check(tab, """
        (function() {
            // PChome 24h 使用 data-regression 標記購買按鈕
            var selectors = [
                'button[data-regression="product_button_buyNow"]',
                'button[data-regression="product_button_addToCart"]',
                '#buy-btn', '.buy-btn', '#btn-buy', '.btn-buy',
            ];
            for (var s of selectors) {
                var el = document.querySelector(s);
                if (el) {
                    var soldOut = el.disabled ||
                                  el.classList.contains('disabled') ||
                                  el.classList.contains('no-stock') ||
                                  el.textContent.trim().includes('缺貨') ||
                                  el.textContent.trim().includes('售完') ||
                                  el.textContent.trim().includes('補貨中');
                    return { found: true, disabled: soldOut, text: el.textContent.trim() };
                }
            }
            return { found: false, disabled: true, text: '' };
        })()
    """)


async def _click_buy(tab, config_dict):
    debug = util.create_debug_logger(config_dict)
    clicked = await evaluate_with_pause_check(tab, """
        (function() {
            function fireClick(el) {
                el.click();
                el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
                el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
                el.dispatchEvent(new MouseEvent('click', {bubbles:true}));
            }
            var selectors = [
                'button[data-regression="product_button_buyNow"]',
                'button[data-regression="product_button_addToCart"]',
                '#buy-btn', '.buy-btn', '#btn-buy', '.btn-buy',
            ];
            for (var s of selectors) {
                var el = document.querySelector(s);
                if (el && !el.disabled && !el.classList.contains('disabled') && !el.classList.contains('no-stock')) {
                    fireClick(el);
                    return el.textContent.trim();
                }
            }
            return null;
        })()
    """)
    if clicked:
        debug.log(f"[PCHOME] 已點擊: {clicked}")
        play_sound_while_ordering(config_dict)
        send_discord_notification(config_dict, "ticket", "PChome")
        send_telegram_notification(config_dict, "ticket", "PChome")
        return True
    return False


async def _handle_cart(tab, config_dict):
    """購物車頁：點擊結帳按鈕"""
    debug = util.create_debug_logger(config_dict)
    await asyncio.sleep(random.uniform(1.0, 1.5))
    clicked = await evaluate_with_pause_check(tab, """
        (function() {
            var selectors = [
                '#cart-checkout-btn',
                '.checkout-btn',
                'button[class*="checkout"]',
                'a[class*="checkout"]',
            ];
            for (var s of selectors) {
                var el = document.querySelector(s);
                if (el && !el.disabled) { el.click(); return el.textContent.trim(); }
            }
            var btn = Array.from(document.querySelectorAll('button, a')).find(b =>
                (b.textContent || '').trim().includes('去結帳') ||
                (b.textContent || '').trim().includes('前往結帳') ||
                (b.textContent || '').trim().includes('結帳')
            );
            if (btn && !btn.disabled) { btn.click(); return btn.textContent.trim(); }
            return null;
        })()
    """)
    if clicked:
        debug.log(f"[PCHOME] 購物車→點擊結帳: {clicked}")
    else:
        debug.log("[PCHOME] 購物車頁找不到結帳按鈕")


async def _handle_checkout(tab, config_dict):
    """結帳頁：選信用卡一次付清、填 CVV、送出訂單"""
    debug = util.create_debug_logger(config_dict)
    cvv = config_dict.get("accounts", {}).get("pchome_cvv", "")
    await asyncio.sleep(random.uniform(1.5, 2.0))

    # 偵測頁面 DOM 結構（debug 用）
    dom_info = await evaluate_with_pause_check(tab, """
        (function() {
            var radios = Array.from(document.querySelectorAll('input[type="radio"]')).map(r => ({
                id: r.id, name: r.name, value: r.value, checked: r.checked,
                label: (r.closest('label') || r.parentElement || {}).textContent.trim().substring(0,50)
            }));
            var inputs = Array.from(document.querySelectorAll('input[type="text"],input[type="tel"],input[type="number"],input[type="password"]')).map(i => ({
                id: i.id, name: i.name, placeholder: i.placeholder, maxLength: i.maxLength
            }));
            var btns = Array.from(document.querySelectorAll('button,input[type="submit"]')).map(b => ({
                id: b.id, cls: b.className.substring(0,40), text: (b.textContent||b.value||'').trim().substring(0,30)
            }));
            return { radios: radios, inputs: inputs, btns: btns };
        })()
    """)
    debug.log(f"[PCHOME] payinfo DOM: {dom_info}")

    # Step 1: 選擇「信用卡一次付清」(id='CC')
    selected = await evaluate_with_pause_check(tab, """
        (function() {
            var cc = document.querySelector('#CC');
            if (cc && !cc.checked) {
                cc.click();
                cc.dispatchEvent(new Event('change', {bubbles:true}));
                return 'clicked #CC';
            }
            if (cc && cc.checked) return 'already checked';
            // fallback: 找 label 包含「一次付清」
            var lbl = Array.from(document.querySelectorAll('label')).find(l => l.textContent.includes('一次付清'));
            if (lbl) { lbl.click(); return 'clicked label'; }
            return null;
        })()
    """)
    debug.log(f"[PCHOME] 選付款方式: {selected}")
    # 等 CVV 欄位出現
    await asyncio.sleep(random.uniform(1.5, 2.0))

    # Step 2: 填 CVV（CVV 欄位在選完信用卡後才出現）
    if cvv:
        filled = await evaluate_with_pause_check(tab, f"""
            (function() {{
                var candidates = [
                    document.querySelector('#cvv'),
                    document.querySelector('input[name="cvv"]'),
                    document.querySelector('input[name="CVV"]'),
                    document.querySelector('input[placeholder*="CVV"]'),
                    document.querySelector('input[placeholder*="cvv"]'),
                    document.querySelector('input[placeholder*="安全碼"]'),
                    document.querySelector('input[placeholder*="卡片"]'),
                    document.querySelector('input[placeholder*="背面"]'),
                ];
                var cvvInput = candidates.find(i => i != null);
                if (!cvvInput) {{
                    cvvInput = Array.from(document.querySelectorAll('input[type="text"],input[type="tel"],input[type="number"],input[type="password"]'))
                        .find(i => i.maxLength === 3 || i.maxLength === 4);
                }}
                if (cvvInput) {{
                    cvvInput.focus();
                    cvvInput.value = {repr(cvv)};
                    cvvInput.dispatchEvent(new Event('input', {{bubbles:true}}));
                    cvvInput.dispatchEvent(new Event('change', {{bubbles:true}}));
                    return true;
                }}
                return false;
            }})()
        """)
        debug.log(f"[PCHOME] CVV 填入: {filled}")
        await asyncio.sleep(random.uniform(0.3, 0.5))

    # Step 3: 點擊「確認付款」
    submitted = await evaluate_with_pause_check(tab, """
        (function() {
            function fireClick(el) {
                el.click();
                el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
                el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
                el.dispatchEvent(new MouseEvent('click', {bubbles:true}));
            }
            var keywords = ['確認付款','確認下單','送出訂單','立即下單','完成結帳','確認購買','提交訂單'];
            var btn = Array.from(document.querySelectorAll('button, input[type="submit"]')).find(b =>
                keywords.some(k => (b.textContent || b.value || '').trim().includes(k))
            );
            if (btn && !btn.disabled) { fireClick(btn); return (btn.textContent || btn.value || '').trim(); }
            return null;
        })()
    """)
    if submitted:
        debug.log(f"[PCHOME] 已送出訂單: {submitted}")
        play_sound_while_ordering(config_dict)
        send_discord_notification(config_dict, "order", "PChome")
        send_telegram_notification(config_dict, "order", "PChome")
    else:
        debug.log("[PCHOME] 找不到送出按鈕")


async def nodriver_pchome_main(tab, url, config_dict):
    debug = util.create_debug_logger(config_dict)

    if _state["purchase_done"]:
        return

    if await check_and_handle_pause(config_dict):
        return

    # 節流：每 2 秒才執行一次，避免 429
    now = time.time()
    if now - _state["last_check_time"] < 2.0:
        return
    _state["last_check_time"] = now

    if await _is_login_page(tab):
        if not _state["signed_in"]:
            await _do_login(tab, config_dict)
            _state["signed_in"] = True
        return

    # 訂單完成頁
    if '/checkout/result' in url or '/order/complete' in url or 'orderComplete' in url or 'thankYou' in url:
        if not _state["purchase_done"]:
            debug.log("[PCHOME] 訂單完成！")
            play_sound_while_ordering(config_dict)
            _state["purchase_done"] = True
        return

    # PChome 真實購物車 URL: ecssl.pchome.com.tw/fsrwd/cart
    is_cart_url = (('/fsrwd/cart' in url or '/cart/' in url or url.endswith('/cart'))
                   and '/payinfo' not in url and '/confirm' not in url)
    # PChome 真實結帳 URL: /fsrwd/cart/payinfo 或 /checkout/
    is_checkout_url = '/payinfo' in url or '/checkout/' in url or '/confirm' in url

    # 結帳頁（填 CVV + 送出）
    if is_checkout_url and 'result' not in url and 'complete' not in url:
        if not _state["checkout_handled"]:
            await _handle_checkout(tab, config_dict)
            _state["checkout_handled"] = True
        return

    # 購物車頁（點擊「去結帳」）
    if is_cart_url:
        if not _state["cart_handled"]:
            await _handle_cart(tab, config_dict)
            _state["cart_handled"] = True
        return

    # 已點擊，若尚未進入購物車/結帳頁，一律導向購物車（PChome 加入購物車後會跳回首頁）
    if _state["clicked"] and not _state["cart_handled"] and not is_cart_url and not is_checkout_url:
        debug.log(f"[PCHOME] 已點擊，導向購物車 (目前 URL={url})")
        await asyncio.sleep(2.0)
        await tab.get("https://ecssl.pchome.com.tw/fsrwd/cart")
        return

    # 商品頁
    if '/prod/' in url or '/DCPC' in url or 'goodsDetail' in url:
        btn = await _get_buy_button(tab)
        debug.log(f"[PCHOME] _get_buy_button → {btn}")
        if btn and btn.get("found"):
            text = btn.get("text", "")
            disabled = btn.get("disabled", True)
            if text != _state["last_button_text"]:
                debug.log(f"[PCHOME] 按鈕: {text} (disabled={disabled})")
                _state["last_button_text"] = text
            if not disabled and not _state["clicked"]:
                success = await _click_buy(tab, config_dict)
                debug.log(f"[PCHOME] _click_buy → {success}")
                if success:
                    _state["clicked"] = True
                await asyncio.sleep(random.uniform(1.0, 1.5))
        else:
            debug.log(f"[PCHOME] 找不到購買按鈕，URL={url}")
