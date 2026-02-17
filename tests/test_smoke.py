import pytest
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

def test_imports():
    """Smoke test: Verify critical modules can be imported (requirements are correct)."""
    try:
        from app.main import app
        from app.core.config import settings
        from app.services.gemini import gemini_service
        import google.genai
        assert True
    except ImportError as e:
        pytest.fail(f"Import failed: {e}")

@pytest.mark.asyncio
async def test_admin_auth_bypass_dev():
    """Verify admin auth allows access in dev mode without key."""
    from app.api.routes.admin import verify_admin_key
    from app.core.config import settings
    
    # Mock settings
    original_mode = settings.ENV_MODE
    original_key = settings.ADMIN_API_KEY
    
    try:
        settings.ENV_MODE = "dev"
        settings.ADMIN_API_KEY = None
        
        # Should not raise exception
        await verify_admin_key(x_admin_key=None)
        assert True
    finally:
        settings.ENV_MODE = original_mode
        settings.ADMIN_API_KEY = original_key

@pytest.mark.asyncio
async def test_admin_auth_block_prod():
    """Verify admin auth BLOCKS access in prod mode without key."""
    from app.api.routes.admin import verify_admin_key
    from app.core.config import settings
    from fastapi import HTTPException
    
    original_mode = settings.ENV_MODE
    original_key = settings.ADMIN_API_KEY
    
    try:
        settings.ENV_MODE = "prod"
        settings.ADMIN_API_KEY = None
        
        # Should raise 403
        try:
            await verify_admin_key(x_admin_key=None)
            pytest.fail("Should have raised HTTPException(403)")
        except HTTPException as e:
            assert e.status_code == 403
            assert "configured" in e.detail
            
    finally:
        settings.ENV_MODE = original_mode
        settings.ADMIN_API_KEY = original_key
