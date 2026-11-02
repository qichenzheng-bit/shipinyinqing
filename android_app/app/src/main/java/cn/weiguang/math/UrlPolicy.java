package cn.weiguang.math;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

/**
 * Exact HTTPS origin boundary shared by navigation and download code.
 * No javascript bridges, embedded credentials, http downgrades or host suffix checks.
 */
public final class UrlPolicy {
    private UrlPolicy() {}

    public static String normalizeServer(String raw) {
        if (raw == null || raw.trim().isEmpty() || raw.length() > 500) {
            throw new IllegalArgumentException("请输入有效的服务器 HTTPS 地址");
        }
        try {
            URI value = new URI(raw.trim());
            if (!"https".equalsIgnoreCase(value.getScheme())
                    || value.getHost() == null
                    || value.getHost().isEmpty()
                    || value.getRawUserInfo() != null
                    || value.getRawQuery() != null
                    || value.getRawFragment() != null
                    || (value.getRawPath() != null && !value.getRawPath().isEmpty()
                        && !"/".equals(value.getRawPath()))
                    || value.getPort() == 0 || value.getPort() > 65535) {
                throw new IllegalArgumentException("仅支持完整的 HTTPS 服务端根地址");
            }
            String host = value.getHost().toLowerCase(Locale.ROOT);
            String authority = host.contains(":") ? "[" + host + "]" : host;
            int port = value.getPort();
            return "https://" + authority + (port > 0 && port != 443 ? ":" + port : "");
        } catch (URISyntaxException exception) {
            throw new IllegalArgumentException("服务器地址格式不正确", exception);
        }
    }

    public static boolean sameOrigin(String trustedOrigin, String candidate) {
        if (trustedOrigin == null || candidate == null) return false;
        try {
            URI trusted = new URI(trustedOrigin);
            URI url = new URI(candidate);
            if (!"https".equalsIgnoreCase(url.getScheme())
                    || url.getHost() == null
                    || url.getRawUserInfo() != null) {
                return false;
            }
            return trusted.getHost().equalsIgnoreCase(url.getHost())
                    && port(trusted) == port(url);
        } catch (URISyntaxException | NullPointerException exception) {
            return false;
        }
    }

    private static int port(URI uri) {
        return uri.getPort() <= 0 ? 443 : uri.getPort();
    }

    public static boolean approvedDownload(String trustedOrigin, String url) {
        if (!sameOrigin(trustedOrigin, url)) return false;
        try {
            URI uri = new URI(url);
            String path = uri.getRawPath();
            // Only known authenticated download endpoints are allowed to write
            // files to the Android public Downloads directory.
            if (uri.getRawQuery() != null || uri.getRawFragment() != null) return false;
            return "/api/v1/system/edit-history/export".equals(path)
                || (path != null && path.matches(
                    "^/api/v1/videos/[a-zA-Z0-9_-]{1,64}/download$"));
        } catch (URISyntaxException exception) {
            return false;
        }
    }
}
