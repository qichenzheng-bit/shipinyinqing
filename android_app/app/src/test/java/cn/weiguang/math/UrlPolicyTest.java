package cn.weiguang.math;

import org.junit.Test;
import static org.junit.Assert.*;

public final class UrlPolicyTest {
    @Test
    public void onlyHttpsServerRootIsAccepted() {
        assertEquals("https://math.example.com",
                UrlPolicy.normalizeServer(" https://MATH.EXAMPLE.COM/ "));
        assertEquals("https://math.example.com:8443",
                UrlPolicy.normalizeServer("https://math.example.com:8443/"));
        assertEquals("https://math.example.com",
                UrlPolicy.normalizeServer("https://math.example.com:443"));
    }

    @Test
    public void invalidOrMaliciousServerAddressesAreRejected() {
        String[] bad = {
            "", " ", "http://math.example.com", "http://192.168.1.3:8000",
            "http://localhost:8000", "file:///etc/passwd", "javascript:alert(1)",
            "https://user:password@math.example.com", "https://math.example.com/a",
            "https://math.example.com?a=123", "https://math.example.com#key",
            "https://math.example.com.evil.tld/maths",
            "https://math.example.com:99999",
        };
        for (String value : bad) {
            try {
                UrlPolicy.normalizeServer(value);
                fail("Unsafe endpoint was accepted: " + value);
            } catch (IllegalArgumentException expected) {
                // The login cookie can only flow to an explicitly entered HTTPS root.
            }
        }
    }

    @Test
    public void exactOriginNavigationNeverUsesSuffixComparison() {
        String origin = "https://math.example.com";
        assertTrue(UrlPolicy.sameOrigin(origin,
                "https://math.example.com/api/v1/videos"));
        assertTrue(UrlPolicy.sameOrigin(origin, "https://math.example.com:443/"));
        for (String target : new String[]{
                "http://math.example.com/",
                "https://math.example.com.evil.tld/",
                "https://evil-math.example.com/",
                "https://math.example.com:8443/",
                "file:///sdcard/private",
                "javascript:alert('hello')",
        }) {
            assertFalse("Disallowed navigation: " + target,
                    UrlPolicy.sameOrigin(origin, target));
        }
    }

    @Test
    public void onlyAuthenticatedVideoAndJsonExportCanBeDownloaded() {
        String origin = "https://math.example.com";
        assertTrue(UrlPolicy.approvedDownload(origin,
                "https://math.example.com/api/v1/videos/Ab12cd34/download"));
        assertTrue(UrlPolicy.approvedDownload(origin,
                "https://math.example.com/api/v1/system/edit-history/export"));
        assertFalse(UrlPolicy.approvedDownload(origin,
                "https://math.example.com/admin/credentials"));
        assertFalse(UrlPolicy.approvedDownload(origin,
                "https://attacker.tld/api/v1/videos/Ab12cd34/download"));
        assertFalse(UrlPolicy.approvedDownload(origin,
                "https://math.example.com/api/v1/videos/Ab12cd34/download?redirect=x"));
        assertFalse(UrlPolicy.approvedDownload(origin, "blob:https://math.example.com/a"));
    }
}
