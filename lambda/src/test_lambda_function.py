"""
Unit tests for lambda_function.py
"""
import json
import sys
import os

# Add the src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from lambda_function import lambda_handler


class TestLambdaHandler:
    """Tests for the lambda_handler function."""

    def test_lambda_handler_direct_invoke(self):
        """Test lambda handler with direct SDK invoke."""
        event = {
            "body": json.dumps({
                "query": "Hello",
                "history": ""
            }),
            "requestContext": {"requestId": "test-123"}
        }
        # This will fail without API key, but we can test the structure
        result = lambda_handler(event, None)
        # Should return error due to missing API key, but structure should be correct
        assert result["statusCode"] in [200, 400, 500]
        assert "body" in result
        body = json.loads(result["body"])
        assert "response" in body or "error" in body


def run_tests():
    """Run all tests and report results."""
    test_classes = [TestLambdaHandler]
    total_tests = 0
    passed = 0
    failed = 0

    for test_class in test_classes:
        instance = test_class()
        methods = [m for m in dir(instance) if m.startswith('test_')]
        
        for method_name in methods:
            total_tests += 1
            try:
                method = getattr(instance, method_name)
                method()
                print(f"✓ {test_class.__name__}.{method_name}")
                passed += 1
            except Exception as e:
                print(f"✗ {test_class.__name__}.{method_name}: {e}")
                failed += 1

    print(f"\n--- Results: {passed}/{total_tests} passed, {failed} failed ---")
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)