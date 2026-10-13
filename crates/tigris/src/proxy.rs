use std::net::SocketAddr;
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use tokio::net::TcpStream;
use url::Url;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum ProxyConfig {
    Direct,
    Http {
        host: String,
        port: u16,
        auth: Option<(String, String)>,
    },
    Socks4 {
        host: String,
        port: u16,
        user_id: Option<String>,
    },
    Socks5 {
        host: String,
        port: u16,
        auth: Option<(String, String)>,
    },
}

impl ProxyConfig {
    /// Parses proxy configuration from a URL string like:
    /// - socks5://user:pass@127.0.0.1:1080
    /// - socks4://127.0.0.1:1080
    /// - http://user:pass@127.0.0.1:8080
    pub fn parse(s: &str) -> Result<Self> {
        let s = s.trim();
        if s.is_empty() || s.eq_ignore_ascii_case("direct") {
            return Ok(Self::Direct);
        }

        let parsed = Url::parse(s).context("Invalid proxy URL format")?;
        let host = parsed.host_str().context("Missing proxy host")?.to_string();
        let port = parsed.port().context("Missing proxy port")?;

        let auth = if !parsed.username().is_empty() || parsed.password().is_some() {
            Some((
                parsed.username().to_string(),
                parsed.password().unwrap_or_default().to_string(),
            ))
        } else {
            None
        };

        match parsed.scheme().to_lowercase().as_str() {
            "http" | "https" => Ok(Self::Http { host, port, auth }),
            "socks4" | "socks4a" => Ok(Self::Socks4 {
                host,
                port,
                user_id: auth.map(|(u, _)| u),
            }),
            "socks5" | "socks5h" => Ok(Self::Socks5 { host, port, auth }),
            other => anyhow::bail!("Unsupported proxy scheme: '{}'. Use http, socks4, or socks5.", other),
        }
    }

    /// Builds a configured `reqwest::Client` respecting this proxy setting.
    pub fn build_client(&self, timeout_secs: u64) -> Result<reqwest::Client> {
        let mut builder = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(timeout_secs))
            .pool_idle_timeout(std::time::Duration::from_secs(30));

        match self {
            Self::Direct => {
                // Direct connection, no proxy
                builder = builder.no_proxy();
            }
            Self::Http { host, port, auth } => {
                let proxy_url = format!("http://{}:{}", host, port);
                let mut proxy = reqwest::Proxy::all(&proxy_url)?;
                if let Some((user, pass)) = auth {
                    proxy = proxy.basic_auth(user, pass);
                }
                builder = builder.proxy(proxy);
            }
            Self::Socks5 { host, port, auth } => {
                let proxy_url = if let Some((user, pass)) = auth {
                    format!("socks5://{}:{}@{}:{}", user, pass, host, port)
                } else {
                    format!("socks5://{}:{}", host, port)
                };
                let proxy = reqwest::Proxy::all(&proxy_url)?;
                builder = builder.proxy(proxy);
            }
            Self::Socks4 { host, port, user_id: _ } => {
                // Note: Reqwest's underlying proxy supports SOCKS5 natively.
                // For SOCKS4, we configure via socks4://
                let proxy_url = format!("socks4://{}:{}", host, port);
                let proxy = reqwest::Proxy::all(&proxy_url)?;
                builder = builder.proxy(proxy);
            }
        }

        Ok(builder.build()?)
    }

    /// Establishes an async raw TCP tunnel to a remote destination through this proxy.
    pub async fn connect_tunnel(&self, target_host: &str, target_port: u16) -> Result<TcpStream> {
        match self {
            Self::Direct => {
                let addr = format!("{}:{}", target_host, target_port);
                TcpStream::connect(&addr).await.context("Direct connection failed")
            }
            Self::Http { host, port, auth } => {
                let proxy_addr = format!("{}:{}", host, port);
                let mut stream = TcpStream::connect(&proxy_addr).await.context("HTTP proxy connect failed")?;

                let mut req = format!(
                    "CONNECT {}:{} HTTP/1.1\r\nHost: {}:{}\r\n",
                    target_host, target_port, target_host, target_port
                );
                if let Some((user, pass)) = auth {
                    use base64::Engine;
                    let credentials = format!("{}:{}", user, pass);
                    let encoded = base64::engine::general_purpose::STANDARD.encode(credentials);
                    req.push_str(&format!("Proxy-Authorization: Basic {}\r\n", encoded));
                }
                req.push_str("\r\n");

                use tokio::io::{AsyncReadExt, AsyncWriteExt};
                stream.write_all(req.as_bytes()).await?;

                let mut buf = [0u8; 1024];
                let n = stream.read(&mut buf).await?;
                let resp = String::from_utf8_lossy(&buf[..n]);
                if !resp.starts_with("HTTP/1.1 200") && !resp.starts_with("HTTP/1.0 200") {
                    anyhow::bail!("HTTP proxy rejected CONNECT tunnel: {}", resp);
                }
                Ok(stream)
            }
            Self::Socks5 { host, port, auth } => {
                let proxy_addr = (host.as_str(), *port);
                match auth {
                    Some((user, pass)) => {
                        let stream = tokio_socks::tcp::Socks5Stream::connect_with_password(
                            proxy_addr,
                            (target_host, target_port),
                            user,
                            pass,
                        )
                        .await
                        .context("SOCKS5 authenticated connect failed")?;
                        Ok(stream.into_inner())
                    }
                    None => {
                        let stream = tokio_socks::tcp::Socks5Stream::connect(
                            proxy_addr,
                            (target_host, target_port),
                        )
                        .await
                        .context("SOCKS5 connect failed")?;
                        Ok(stream.into_inner())
                    }
                }
            }
            Self::Socks4 { host, port, user_id } => {
                use tokio::io::{AsyncReadExt, AsyncWriteExt};
                let proxy_addr = format!("{}:{}", host, port);
                let mut stream = TcpStream::connect(&proxy_addr).await.context("SOCKS4 proxy connect failed")?;

                let target_ips = tokio::net::lookup_host(format!("{}:{}", target_host, target_port)).await?;
                let target_ip = target_ips.into_iter().next().context("Failed to resolve target IP")?;

                if let SocketAddr::V4(v4) = target_ip {
                    let mut packet = vec![0x04, 0x01]; // SOCKS4 CONNECT
                    packet.extend_from_slice(&target_port.to_be_bytes());
                    packet.extend_from_slice(&v4.ip().octets());
                    if let Some(uid) = user_id {
                        packet.extend_from_slice(uid.as_bytes());
                    }
                    packet.push(0x00);

                    stream.write_all(&packet).await?;
                    let mut resp = [0u8; 8];
                    stream.read_exact(&mut resp).await?;
                    if resp[1] != 0x5A {
                        anyhow::bail!("SOCKS4 request rejected: code 0x{:02X}", resp[1]);
                    }
                    Ok(stream)
                } else {
                    anyhow::bail!("SOCKS4 only supports IPv4 addresses; use SOCKS5 for IPv6");
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_proxies() {
        assert_eq!(ProxyConfig::parse("direct").unwrap(), ProxyConfig::Direct);
        
        match ProxyConfig::parse("socks5://admin:secret@127.0.0.1:1080").unwrap() {
            ProxyConfig::Socks5 { host, port, auth } => {
                assert_eq!(host, "127.0.0.1");
                assert_eq!(port, 1080);
                assert_eq!(auth, Some(("admin".to_string(), "secret".to_string())));
            }
            _ => panic!("Expected Socks5"),
        }

        match ProxyConfig::parse("http://user:pass@proxy.example.com:8080").unwrap() {
            ProxyConfig::Http { host, port, auth } => {
                assert_eq!(host, "proxy.example.com");
                assert_eq!(port, 8080);
                assert_eq!(auth, Some(("user".to_string(), "pass".to_string())));
            }
            _ => panic!("Expected Http"),
        }
    }
}
