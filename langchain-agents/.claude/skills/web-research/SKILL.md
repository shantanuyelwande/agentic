---
name: web-research
description: Research topics online with verification and citations. Use when you need to gather information from multiple sources, verify facts, and provide credible findings.
---

# Web Research Skill

This skill guides you through thorough research: finding information, verifying facts across sources, and presenting findings with proper citations.

## Research Methodology

### Step 1: Define Research Scope
- What information do you need?
- What are the key questions?
- What would count as reliable sources?

### Step 2: Search and Gather
```bash
# Use WebSearch or WebFetch tools to find:
# - Primary sources (original research, official docs)
# - Secondary sources (reputable analyses)
# - Multiple perspectives on the topic
```

### Step 3: Verify and Cross-Reference
- Check multiple sources for consistency
- Note publication dates and source credibility
- Distinguish between facts, opinions, and claims
- Flag contradictions or uncertainties

### Step 4: Organize Findings
```bash
# Group by:
# - Topic area
# - Source credibility
# - Confidence level (verified, likely, uncertain)
```

### Step 5: Report with Citations
- Summarize findings with clear citations
- Link each claim to its source
- Flag areas needing additional verification
- Highlight insights that span multiple sources

## Best Practices

### Prioritize Sources
1. **Primary sources** - Original research, official documentation, firsthand accounts
2. **Secondary sources** - Analysis by reputable experts citing primary sources
3. **Avoid** - Aggregated content that doesn't cite sources, opinion pieces

### Verify Facts
- Cross-reference key claims across 2+ independent sources
- Check for recent updates (dates matter)
- Note if sources contradict each other
- Be explicit about confidence levels

### Distinguish Information Types
- **Facts**: Verifiable, cited, consistent across sources
- **Claims**: Assertions that need verification
- **Opinions**: Subjective takes, even from experts
- **Analysis**: Interpretation of facts with reasoning

## Example Research Structure

```
Topic: Browser Automation Tools for AI

## Key Findings

### Playwright MCP
- **Fact**: Provides 40+ tools for browser automation (source: playwright.dev)
- **Finding**: More token-efficient than vision-based approaches (source: benchmark)
- **Limitation**: Less suitable for complex reasoning tasks (opinion across multiple sources)

### Browser-Use
- **Fact**: Integrates LLM backend for autonomous task completion (source: github.com/browser-use)
- **Strength**: Good for multi-step reasoning tasks (verified across comparison articles)
- **Cost**: Requires LLM API, ~$0.02-0.05 per task (source: cost comparisons)

## Contradictions Found
- Browser-use vs Playwright: different design philosophies, not directly comparable

## Sources
- [Playwright Docs](https://playwright.dev) - official documentation
- [Browser Use GitHub](https://github.com/browser-use/browser-use) - official repo
- [Benchmarks 2026](https://ytyng.com/...) - comparative analysis
```

## Common Research Patterns

### Competitive Analysis
1. Identify 3-5 competitors
2. Find their key features
3. Compare pricing models
4. Note market positioning
5. Verify with recent news

### Technology Evaluation
1. Find official documentation
2. Check community feedback
3. Look for benchmarks
4. Read case studies
5. Note limitations

### Topic Deep-Dive
1. Find overview sources
2. Identify subtopics
3. Gather expert perspectives
4. Note historical context
5. Flag areas of disagreement

## Tools Used with This Skill

- **WebSearch**: Find initial sources and verify claims
- **WebFetch**: Read full content from credible sources
- **Read/Bash**: Process and organize information
- **data-extraction**: Parse and structure findings

## What Counts as Done

- ✅ Findings are cited with sources
- ✅ Multiple sources consulted for key claims
- ✅ Contradictions are flagged
- ✅ Confidence levels are clear
- ✅ Recent information (dates noted)
- ✅ Distinction between fact/opinion/analysis

- ❌ Single-source claims without verification
- ❌ Outdated information without noting age
- ❌ Opinions presented as facts
- ❌ Vague attribution ("some say...")
- ❌ Missing links to sources
