"""
Bengal Download Manager - Site Grabber Subsystem
================================================
Provides asynchronous web site crawling, link extraction, pattern filtering,
and batch download queue integration.
"""

from core.grabber.crawler import GrabberCrawler, is_private_or_loopback_host

__all__ = ["GrabberCrawler", "is_private_or_loopback_host"]
