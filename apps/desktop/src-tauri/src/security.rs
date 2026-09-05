use url::Url;

pub fn navigation_allowed(url: &Url, development: bool) -> bool {
    let packaged = matches!(
        (url.scheme(), url.host_str(), url.port()),
        ("tauri", Some("localhost"), None)
            | ("http", Some("tauri.localhost"), None)
            | ("https", Some("tauri.localhost"), None)
    );
    let dev = development
        && matches!(
            (url.scheme(), url.host_str(), url.port_or_known_default()),
            ("http", Some("localhost"), Some(5173))
                | ("http", Some("127.0.0.1"), Some(5173))
        );
    packaged || dev
}

#[cfg(test)]
mod tests {
    use url::Url;

    use super::navigation_allowed;

    #[test]
    fn packaged_navigation_rejects_remote_and_loopback_hub_pages() {
        assert!(navigation_allowed(
            &Url::parse("http://tauri.localhost/index.html").unwrap(),
            false
        ));
        assert!(!navigation_allowed(
            &Url::parse("https://example.com/").unwrap(),
            false
        ));
        assert!(!navigation_allowed(
            &Url::parse("http://127.0.0.1:49210/").unwrap(),
            false
        ));
    }

    #[test]
    fn development_navigation_only_allows_fixed_vite_origin() {
        assert!(navigation_allowed(
            &Url::parse("http://localhost:5173/").unwrap(),
            true
        ));
        assert!(!navigation_allowed(
            &Url::parse("http://localhost:4173/").unwrap(),
            true
        ));
    }
}

