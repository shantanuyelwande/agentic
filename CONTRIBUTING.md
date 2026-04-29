# Contributing to Claude Managed Agents

We welcome contributions! This document explains how to help.

## Getting Started

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make changes
4. Test thoroughly
5. Submit a pull request

## Code Style

- Follow PEP 8 for Python code
- Use type hints where possible
- Format with `black`: `black .`
- Lint with `ruff`: `ruff check .`

## Adding Custom Tools

1. Add function to `tools/custom_tools.py`
2. Include docstring with Args/Returns
3. Add input validation
4. Add to `tools/__init__.py`
5. Test with `client.py`

Example:
```python
def my_new_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Brief description of what this tool does.
    
    Args:
        param_name (type): Description
    
    Returns:
        Tool response dict with content blocks
    """
    param = args.get("param_name", "")
    
    # Validate
    if not param:
        return {"content": [{"type": "text", "text": "Error: param required"}], "is_error": True}
    
    # Process
    result = process(param)
    
    # Return
    return {"content": [{"type": "text", "text": json.dumps(result)}]}
```

## Extending Browser Automation

The `browse_web` tool uses Playwright under the hood. To extend it:

```python
# tools/custom_tools.py

async def advanced_browser_task(args: Dict[str, Any]) -> Dict[str, Any]:
    """Advanced browser automation with custom logic."""
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto(args.get("url"))
        
        # Custom automation logic
        await page.click(args.get("selector"))
        await page.fill("#email", args.get("email"))
        
        # Extract results
        result = await page.evaluate("() => document.body.innerText")
        
        await browser.close()
        
        return {
            "content": [{"type": "text", "text": result}]
        }
```

## Browser Tool Guidelines

When developing browser tools:
- ✅ Use `headless=True` for Docker compatibility
- ✅ Set timeouts to prevent hanging
- ✅ Clean up resources (close browser/page)
- ✅ Handle JavaScript loading delays
- ✅ Validate URLs and selectors
- ❌ Don't hardcode credentials
- ❌ Don't assume GUI availability

## Testing

```bash
# Test the client
python client.py

# Run specific test
docker-compose up -d
python -m pytest tests/test_orchestrator.py -v

# Check code quality
black --check .
ruff check .
```

## Documentation

- Update README.md for user-facing changes
- Add docstrings to all functions
- Include type hints
- Document new environment variables

## Submitting Changes

1. Write descriptive commit messages
2. Reference issues if applicable: "Fixes #123"
3. Describe what changed and why
4. Include testing steps
5. Request review from maintainers

## Code Review

All PRs must be reviewed before merging. Reviewers check:
- Code quality and style
- Test coverage
- Documentation
- Security considerations
- Performance impact

## Areas for Contribution

- **Tools**: Add new useful tools
- **Documentation**: Improve guides and examples
- **Features**: MCP integration, WebUI, K8s operators
- **Bug Fixes**: Report and fix issues
- **Tests**: Improve test coverage
- **Examples**: Add usage examples

## Questions?

- Check README.md for common questions
- Review existing issues/discussions
- Open a new discussion for questions

Thank you for contributing!
