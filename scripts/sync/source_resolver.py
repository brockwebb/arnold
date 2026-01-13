#!/usr/bin/env python3
"""
Source Resolver - Config-driven data source priority resolution.

Reads config/sources.yaml and provides functions to determine which data source
to use when multiple sources provide the same metric.

Usage:
    from source_resolver import SourceResolver
    
    resolver = SourceResolver()
    
    # Get preferred source for a metric
    source = resolver.get_preferred_source('hrv', ['apple_watch', 'ultrahuman'])
    # Returns: 'ultrahuman'
    
    # Check if a source should be used for a metric
    if resolver.should_use_source('ultrahuman', 'hrv'):
        # Process ultrahuman HRV data
    
    # Get full metric config
    config = resolver.get_metric_config('hrv')
    # Returns: {'primary': 'ultrahuman', 'fallback': [], 'algorithm': 'rmssd', ...}

CLI:
    python source_resolver.py --validate          # Validate config file
    python source_resolver.py --show hrv          # Show config for metric
    python source_resolver.py --list-sources      # List registered sources
    python source_resolver.py --list-metrics      # List configured metrics
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml


# Default config location
CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "sources.yaml"


class SourceResolver:
    """Resolves data source priorities from configuration."""
    
    def __init__(self, config_path: Optional[Path] = None):
        """Load configuration from YAML file.
        
        Args:
            config_path: Path to sources.yaml. Defaults to config/sources.yaml.
        """
        self.config_path = config_path or CONFIG_PATH
        self._config = None
        self._load_config()
    
    def _load_config(self) -> None:
        """Load and parse the YAML configuration."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        with open(self.config_path) as f:
            self._config = yaml.safe_load(f)
        
        if self._config is None:
            raise ValueError(f"Empty or invalid config file: {self.config_path}")
    
    def reload(self) -> None:
        """Reload configuration from disk."""
        self._load_config()
    
    @property
    def registered_sources(self) -> Dict[str, Any]:
        """Get all registered data sources."""
        return self._config.get("registered_sources", {})
    
    @property
    def metrics(self) -> Dict[str, Any]:
        """Get all metric configurations."""
        return self._config.get("metrics", {})
    
    @property
    def clinical(self) -> Dict[str, Any]:
        """Get clinical data configurations."""
        return self._config.get("clinical", {})
    
    @property
    def training(self) -> Dict[str, Any]:
        """Get training data configurations."""
        return self._config.get("training", {})
    
    def get_metric_config(self, metric: str) -> Optional[Dict[str, Any]]:
        """Get full configuration for a metric.
        
        Args:
            metric: Metric name (e.g., 'hrv', 'resting_hr', 'sleep')
            
        Returns:
            Dict with primary, fallback, algorithm, unit, grain, notes
            or None if metric not found.
        """
        return self.metrics.get(metric)
    
    def get_preferred_source(self, metric: str, available_sources: List[str]) -> Optional[str]:
        """Determine which source to use for a metric.
        
        Args:
            metric: Metric name (e.g., 'hrv', 'resting_hr')
            available_sources: List of sources that have data for this metric
            
        Returns:
            The preferred source name, or None if no configured source is available.
        """
        config = self.get_metric_config(metric)
        if config is None:
            return None
        
        primary = config.get("primary")
        fallback = config.get("fallback", [])
        
        # Check primary first
        if primary in available_sources:
            return primary
        
        # Try fallbacks in order
        for source in fallback:
            if source in available_sources:
                return source
        
        return None
    
    def should_use_source(self, source: str, metric: str) -> bool:
        """Check if a source should be used for a metric.
        
        This is used by analytics queries to filter data.
        
        Args:
            source: Source name to check
            metric: Metric name
            
        Returns:
            True if this source is primary or in fallback list for the metric.
        """
        config = self.get_metric_config(metric)
        if config is None:
            return True  # No config = allow all sources
        
        primary = config.get("primary")
        fallback = config.get("fallback", [])
        
        return source == primary or source in fallback
    
    def get_primary_source(self, metric: str) -> Optional[str]:
        """Get the primary (preferred) source for a metric.
        
        Args:
            metric: Metric name
            
        Returns:
            Primary source name, or None if metric not configured.
        """
        config = self.get_metric_config(metric)
        if config is None:
            return None
        return config.get("primary")
    
    def get_source_info(self, source: str) -> Optional[Dict[str, Any]]:
        """Get information about a registered source.
        
        Args:
            source: Source identifier
            
        Returns:
            Dict with name, type, metrics_provided, notes
            or None if source not registered.
        """
        return self.registered_sources.get(source)
    
    def is_valid_source(self, source: str) -> bool:
        """Check if a source is registered in the config."""
        return source in self.registered_sources
    
    def get_sources_for_metric(self, metric: str) -> List[str]:
        """Get all sources that can provide a metric (primary + fallbacks).
        
        Args:
            metric: Metric name
            
        Returns:
            List of source names, primary first.
        """
        config = self.get_metric_config(metric)
        if config is None:
            return []
        
        sources = []
        primary = config.get("primary")
        if primary:
            sources.append(primary)
        sources.extend(config.get("fallback", []))
        
        return sources
    
    def validate(self) -> List[str]:
        """Validate the configuration file.
        
        Returns:
            List of error messages. Empty list if valid.
        """
        errors = []
        
        # Check registered_sources exists
        if not self.registered_sources:
            errors.append("No registered_sources defined")
        
        # Check metrics exist
        if not self.metrics:
            errors.append("No metrics defined")
        
        # Validate each metric's sources are registered
        for metric_name, config in self.metrics.items():
            primary = config.get("primary")
            if primary and not self.is_valid_source(primary):
                errors.append(
                    f"Metric '{metric_name}': primary source '{primary}' not in registered_sources"
                )
            
            for fallback in config.get("fallback", []):
                if not self.is_valid_source(fallback):
                    errors.append(
                        f"Metric '{metric_name}': fallback source '{fallback}' not in registered_sources"
                    )
        
        # Check for sources that provide metrics but aren't used
        for source_name, source_info in self.registered_sources.items():
            provided = source_info.get("metrics_provided", [])
            used_for = []
            for metric_name, config in self.metrics.items():
                if config.get("primary") == source_name or source_name in config.get("fallback", []):
                    used_for.append(metric_name)
            
            # This is a warning, not an error
            # Could add warnings list if needed
        
        return errors
    
    def get_algorithm_warning(self, metric: str, from_source: str, to_source: str) -> Optional[str]:
        """Check if switching sources would cause algorithm incompatibility.
        
        Args:
            metric: Metric name
            from_source: Current source
            to_source: Proposed new source
            
        Returns:
            Warning message if incompatible, None if OK.
        """
        # Special case for HRV - this is the main incompatibility we know about
        if metric == "hrv":
            hrv_algorithms = {
                "ultrahuman": "rmssd",
                "oura": "rmssd",
                "apple_watch": "sdnn",
                "garmin": "rmssd",  # Most Garmin uses RMSSD
            }
            
            from_algo = hrv_algorithms.get(from_source, "unknown")
            to_algo = hrv_algorithms.get(to_source, "unknown")
            
            if from_algo != to_algo and from_algo != "unknown" and to_algo != "unknown":
                return (
                    f"WARNING: HRV algorithm mismatch. "
                    f"{from_source} uses {from_algo.upper()}, "
                    f"{to_source} uses {to_algo.upper()}. "
                    f"These are NOT comparable - trend history will have discontinuity."
                )
        
        return None


def main():
    """CLI for source resolver."""
    parser = argparse.ArgumentParser(description="Source priority resolver")
    parser.add_argument("--validate", action="store_true", help="Validate config file")
    parser.add_argument("--show", metavar="METRIC", help="Show config for a metric")
    parser.add_argument("--list-sources", action="store_true", help="List registered sources")
    parser.add_argument("--list-metrics", action="store_true", help="List configured metrics")
    parser.add_argument("--config", type=Path, help="Path to config file")
    
    args = parser.parse_args()
    
    try:
        resolver = SourceResolver(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    if args.validate:
        errors = resolver.validate()
        if errors:
            print("Validation FAILED:")
            for error in errors:
                print(f"  ✗ {error}")
            sys.exit(1)
        else:
            print("✓ Configuration valid")
            print(f"  Sources: {len(resolver.registered_sources)}")
            print(f"  Metrics: {len(resolver.metrics)}")
            sys.exit(0)
    
    elif args.show:
        config = resolver.get_metric_config(args.show)
        if config is None:
            print(f"Metric '{args.show}' not found", file=sys.stderr)
            sys.exit(1)
        
        print(f"Metric: {args.show}")
        print(f"  Primary: {config.get('primary')}")
        print(f"  Fallback: {config.get('fallback', [])}")
        print(f"  Algorithm: {config.get('algorithm', 'N/A')}")
        print(f"  Unit: {config.get('unit', 'N/A')}")
        print(f"  Grain: {config.get('grain', 'N/A')}")
        if config.get('notes'):
            print(f"  Notes: {config['notes'].strip()}")
    
    elif args.list_sources:
        print("Registered Sources:")
        for name, info in resolver.registered_sources.items():
            print(f"  {name}: {info.get('name', 'N/A')} ({info.get('type', 'unknown')})")
    
    elif args.list_metrics:
        print("Configured Metrics:")
        for name, config in resolver.metrics.items():
            primary = config.get('primary', 'N/A')
            fallback = config.get('fallback', [])
            fallback_str = f" (fallback: {', '.join(fallback)})" if fallback else ""
            print(f"  {name}: {primary}{fallback_str}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
