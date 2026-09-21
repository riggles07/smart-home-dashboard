"""
Phase 5 tests: mobile-responsive UI + Galaxy A7 Lite deployment.

Covers the css/dashboard.css theme, the mobile profile on the dashboard
configuration, and the Galaxy A7 Lite target-device assumptions.
"""
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
CSS_PATH = PROJECT_ROOT / 'css' / 'dashboard.css'
DEPLOY_GUIDE = PROJECT_ROOT / 'docs' / 'MOBILE_DEPLOYMENT.md'

sys.path.insert(0, str(PROJECT_ROOT / 'flows'))


class TestMobileThemeCss:
    """The mobile-responsive theme file (css/dashboard.css)."""

    def test_theme_file_exists(self):
        assert CSS_PATH.exists(), "css/dashboard.css is missing"

    def test_theme_has_dark_base(self):
        css = CSS_PATH.read_text()
        assert '#1a1a2e' in css          # body background
        assert 'box-sizing: border-box' in css.replace(' ', '') or \
               'box-sizing:border-box' in css.replace(' ', '')

    def test_theme_defines_css_variables(self):
        css = CSS_PATH.read_text()
        assert ':root' in css
        for var in ('--shd-bg', '--shd-accent', '--shd-touch-target'):
            assert var in css, f"missing CSS variable {var}"

    def test_theme_has_touch_friendly_targets(self):
        """Controls must be at least 44px -- comfortable on the A7 Lite."""
        css = CSS_PATH.read_text()
        assert '--shd-touch-target: 44px' in css
        assert 'min-height: var(--shd-touch-target)' in css
        assert 'touch-action: manipulation' in css

    def test_tab_links_meet_touch_target(self):
        """Tab navigation links are primary touch controls on mobile.

        They must carry the 44px minimum-height rule (and tap-friendly
        touch-action), not just padding -- padding alone renders ~42px.
        Found by the Phase 5 on-device audit (2026-09-21); regression guard.
        """
        css = CSS_PATH.read_text()
        tab_block = re.search(r'\.ui_tab \.tab-link \{[^}]*\}', css)
        assert tab_block, ".ui_tab .tab-link rule missing from theme"
        assert 'min-height: var(--shd-touch-target)' in tab_block.group(0), \
            ".tab-link lacks the 44px min-height touch-target rule"
        assert 'touch-action: manipulation' in tab_block.group(0), \
            ".tab-link lacks touch-action: manipulation"

    def test_theme_has_viewport_friendly_text_adjust(self):
        """Stop auto text inflate/zoom on rotate."""
        css = CSS_PATH.read_text()
        assert '-webkit-text-size-adjust: 100%' in css

    def test_theme_blocks_horizontal_scroll(self):
        css = CSS_PATH.read_text()
        assert 'overflow-x: hidden' in css

    def test_theme_stacks_rows_into_columns(self):
        """Rows must collapse to a single column on narrow screens."""
        css = CSS_PATH.read_text()
        stacked = re.findall(r'flex-direction: column', css)
        assert stacked, "no column stacking rules found"
        # there must be a media query that flips .ui_row to column
        assert re.search(
            r'@media[^{]*\{[^@]*\.ui_row\s*\{\s*flex-direction:\s*column',
            css, re.S), ".ui_row never stacks in a media query"

    def test_theme_has_breakpoints_for_target_device(self):
        """Breakpoints must cover the A7 Lite portrait (800 CSS px).

        Portrait viewport (800px) must land inside the tablet-portrait
        band, so the 900px breakpoint applies; the 600px and 380px
        bands cover phone and split-screen modes.
        """
        css = CSS_PATH.read_text()
        widths = [int(w) for w in re.findall(r'@media[^{]*max-width:\s*(\d+)px', css)]
        assert 900 in widths, "missing 900px tablet-portrait breakpoint"
        assert 600 in widths, "missing 600px phone breakpoint"
        assert 380 in widths, "missing 380px small-phone breakpoint"

    def test_breakpoint_covers_galaxy_a7_lite_portrait(self):
        """800px portrait viewport must match a max-width media query."""
        css = CSS_PATH.read_text()
        widths = [int(w) for w in re.findall(r'@media[^{]*max-width:\s*(\d+)px', css)]
        assert any(w >= 800 for w in widths), \
            "no breakpoint >= 800px: A7 Lite portrait would get desktop layout"

    def test_theme_has_status_indicators(self):
        css = CSS_PATH.read_text()
        for cls in ('status-ok', 'status-warning', 'status-error'):
            assert cls in css, f"missing {cls}"

    def test_theme_has_pulse_animation(self):
        css = CSS_PATH.read_text()
        assert '@keyframes pulse' in css

    def test_theme_respects_reduced_motion(self):
        css = CSS_PATH.read_text()
        assert 'prefers-reduced-motion: reduce' in css

    def test_theme_scales_table_density(self):
        """Tables must get smaller padding/font on narrow screens."""
        css = CSS_PATH.read_text()
        assert re.search(r'\.ui_table th, \.ui_table td \{[^}]*font-size: 12px', css) or \
               re.search(r'font-size:\s*12px[^@]*', css.split('max-width: 600px')[1])


class TestDashboardMobileProfile:
    """The mobile profile exposed by the dashboard configuration."""

    @pytest.fixture()
    def dashboard(self):
        from flows import dashboard_configuration
        return dashboard_configuration(None)

    def test_layout_is_auto(self, dashboard):
        """'auto' lets the theme re-flow per viewport."""
        assert dashboard['layout'] == 'auto'

    def test_theme_css_is_linked(self, dashboard):
        assert dashboard['css'] == 'css/dashboard.css'

    def test_mobile_profile_exists(self, dashboard):
        assert 'mobile' in dashboard
        mobile = dashboard['mobile']
        assert mobile['target_device'] == 'Samsung Galaxy A7 Lite'

    def test_mobile_profile_viewport_meta(self, dashboard):
        assert dashboard['mobile']['viewport'] == 'width=device-width, initial-scale=1'

    def test_mobile_profile_touch_target(self, dashboard):
        assert dashboard['mobile']['min_touch_target'] == 44

    def test_mobile_profile_breakpoints(self, dashboard):
        bps = dashboard['mobile']['breakpoints']
        assert bps['tablet_portrait'] == 900
        assert bps['phone'] == 600
        assert bps['small_phone'] == 380
        # A7 Lite portrait (800px) covered by the 900px band
        assert bps['tablet_portrait'] >= 800

    def test_python_and_js_mobile_config_match(self):
        """The JS flow and the Python mirror must agree on the profile."""
        js = (PROJECT_ROOT / 'flows' / 'dashboard-configuration.js').read_text()
        assert 'target_device: "Samsung Galaxy A7 Lite"' in js
        assert 'min_touch_target: 44' in js
        assert 'layout: "auto"' in js

    def test_js_flow_links_theme_css(self):
        js = (PROJECT_ROOT / 'flows' / 'dashboard-configuration.js').read_text()
        assert 'css: "css/dashboard.css"' in js


class TestGalaxyA7LiteDeployment:
    """Deployment artifacts for the Galaxy A7 Lite."""

    def test_deployment_guide_exists(self):
        assert DEPLOY_GUIDE.exists(), "docs/MOBILE_DEPLOYMENT.md is missing"

    def test_guide_mentions_target_device(self):
        text = DEPLOY_GUIDE.read_text()
        assert 'Galaxy A7 Lite' in text

    def test_guide_has_access_instructions(self):
        text = DEPLOY_GUIDE.read_text()
        assert '1880' in text          # dashboard port
        assert 'http://' in text

    def test_guide_covers_lan_access(self):
        """Device must reach the dashboard over the LAN, not localhost."""
        text = DEPLOY_GUIDE.read_text()
        assert 'localhost' in text      # documented why NOT to use it