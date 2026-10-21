// Gives the site pop-out its own Windows taskbar identity (AppUserModelID) so it shows as a separate button with its own
// icon instead of grouping under the Suite. Windows only; elsewhere a no-op. Failure is harmless (the window keeps its own
// icon and title, it just may group with the Suite button). See Docs/SITE_POPOUT.md.

#[cfg(windows)]
pub fn set_window_aumid(win: &tauri::WebviewWindow, id: &str) {
    use ::windows::core::{GUID, PWSTR};
    use ::windows::Win32::Foundation::PROPERTYKEY;
    use ::windows::Win32::System::Com::CoTaskMemAlloc;
    use ::windows::Win32::System::Com::StructuredStorage::{PropVariantClear, PROPVARIANT};
    use ::windows::Win32::System::Variant::VARENUM;
    use ::windows::Win32::UI::Shell::PropertiesSystem::{IPropertyStore, SHGetPropertyStoreForWindow};

    // PKEY_AppUserModel_ID {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}, 5
    const PKEY_APPUSERMODEL_ID: PROPERTYKEY = PROPERTYKEY { fmtid: GUID::from_u128(0x9F4C2855_9F79_4B39_A8D0_E1D42DE1D5F3), pid: 5 };
    let Ok(hwnd) = win.hwnd() else { return };
    unsafe {
        let Ok(store) = SHGetPropertyStoreForWindow::<IPropertyStore>(hwnd) else { return };
        // VT_LPWSTR (31) holding a CoTaskMem copy of the id; PropVariantClear frees it
        let wide: Vec<u16> = id.encode_utf16().chain(std::iter::once(0)).collect();
        let mem = CoTaskMemAlloc(wide.len() * 2) as *mut u16;
        if mem.is_null() {
            return;
        }
        std::ptr::copy_nonoverlapping(wide.as_ptr(), mem, wide.len());
        let mut v = PROPVARIANT::default();
        let inner = &mut *v.Anonymous.Anonymous;
        inner.vt = VARENUM(31);
        inner.Anonymous.pwszVal = PWSTR(mem);
        if store.SetValue(&PKEY_APPUSERMODEL_ID, &v).is_ok() {
            let _ = store.Commit();
        }
        let _ = PropVariantClear(&mut v);
    }
}

#[cfg(not(windows))]
pub fn set_window_aumid(_win: &tauri::WebviewWindow, _id: &str) {}
