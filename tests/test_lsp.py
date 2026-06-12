import pytest
from unittest.mock import patch, MagicMock
from jesse.services.lsp import is_lsp_update_available, _compare_versions


class TestVersionComparison:
    """Tests for the version comparison helper function."""
    
    def test_equal_versions(self):
        assert _compare_versions('1.2.3', '1.2.3') == 0
        assert _compare_versions('0.0.1', '0.0.1') == 0
        assert _compare_versions('10.20.30', '10.20.30') == 0
    
    def test_first_version_greater(self):
        assert _compare_versions('1.2.4', '1.2.3') == 1
        assert _compare_versions('2.0.0', '1.9.9') == 1
        assert _compare_versions('1.3.0', '1.2.9') == 1
        assert _compare_versions('10.0.0', '9.9.9') == 1
    
    def test_first_version_lesser(self):
        assert _compare_versions('1.2.3', '1.2.4') == -1
        assert _compare_versions('1.9.9', '2.0.0') == -1
        assert _compare_versions('1.2.9', '1.3.0') == -1
        assert _compare_versions('9.9.9', '10.0.0') == -1
    
    def test_different_length_versions(self):
        assert _compare_versions('1.2', '1.2.0') == 0
        assert _compare_versions('1.2.0', '1.2') == 0
        assert _compare_versions('1.2', '1.2.1') == -1
        assert _compare_versions('1.2.1', '1.2') == 1
        assert _compare_versions('1', '1.0.0') == 0
        assert _compare_versions('2.0', '1.9.9.9') == 1
    
    def test_invalid_version_parts(self):
        # Non-numeric parts should be treated as 0
        assert _compare_versions('1.2.x', '1.2.0') == 0
        assert _compare_versions('1.2.beta', '1.2.1') == -1


class TestLspUpdateAvailable:
    """Tests for the is_lsp_update_available function."""
    
    @patch('jesse.services.lsp._get_lsp_version')
    def test_no_current_version_installed(self, mock_get_version):
        """Should return False when no version is installed."""
        mock_get_version.return_value = ''
        
        result = is_lsp_update_available()
        
        assert result is False
    
    @patch('jesse.services.lsp.requests.get')
    @patch('jesse.services.lsp._get_lsp_version')
    def test_update_available(self, mock_get_version, mock_requests_get):
        """Should return True when a newer version is available."""
        mock_get_version.return_value = '1.2.3'
        
        mock_response = MagicMock()
        mock_response.json.return_value = {'tag_name': 'v1.3.0'}
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        
        result = is_lsp_update_available()
        
        assert result is True
    
    @patch('jesse.services.lsp.requests.get')
    @patch('jesse.services.lsp._get_lsp_version')
    def test_no_update_same_version(self, mock_get_version, mock_requests_get):
        """Should return False when versions are the same."""
        mock_get_version.return_value = '1.2.3'
        
        mock_response = MagicMock()
        mock_response.json.return_value = {'tag_name': 'v1.2.3'}
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        
        result = is_lsp_update_available()
        
        assert result is False
    
    @patch('jesse.services.lsp.requests.get')
    @patch('jesse.services.lsp._get_lsp_version')
    def test_no_update_older_version(self, mock_get_version, mock_requests_get):
        """Should return False when installed version is newer."""
        mock_get_version.return_value = '2.0.0'
        
        mock_response = MagicMock()
        mock_response.json.return_value = {'tag_name': 'v1.9.9'}
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        
        result = is_lsp_update_available()
        
        assert result is False
    
    @patch('jesse.services.lsp.requests.get')
    @patch('jesse.services.lsp._get_lsp_version')
    def test_tag_name_without_v_prefix(self, mock_get_version, mock_requests_get):
        """Should handle tag names without 'v' prefix."""
        mock_get_version.return_value = '1.2.3'
        
        mock_response = MagicMock()
        mock_response.json.return_value = {'tag_name': '1.3.0'}
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        
        result = is_lsp_update_available()
        
        assert result is True
    
    @patch('jesse.services.lsp.requests.get')
    @patch('jesse.services.lsp._get_lsp_version')
    def test_network_error_raises_exception(self, mock_get_version, mock_requests_get):
        """Should raise exception on network errors."""
        mock_get_version.return_value = '1.2.3'
        mock_requests_get.side_effect = Exception("Network error")
        
        with pytest.raises(Exception) as exc_info:
            is_lsp_update_available()
        
        assert "Error checking for LSP update" in str(exc_info.value)
    
    @patch('jesse.services.lsp.requests.get')
    @patch('jesse.services.lsp._get_lsp_version')
    def test_missing_tag_name_in_response(self, mock_get_version, mock_requests_get):
        """Should handle missing tag_name in API response."""
        mock_get_version.return_value = '1.2.3'
        
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        
        result = is_lsp_update_available()
        
        # Should compare with empty string and likely return False
        assert result is False

