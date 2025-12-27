#!/usr/bin/env python3
"""
Arnold CLI - SKYCOACH

Internal Codename: SKYCOACH
Command-line coaching interface for Arnold.

Usage:
    arnold plan [--date DATE] [--focus FOCUS]
    arnold status
    arnold analyze --exercise EXERCISE [--weeks WEEKS]
    arnold alt --exercise EXERCISE [--reason REASON]
    arnold volume [--weeks WEEKS] [--by {muscle,exercise}]
"""

import click
from datetime import date, timedelta
from typing import Optional

from arnold.graph import ArnoldGraph
from arnold.judgment_day import (
    WorkoutPlanner,
    PeriodizationEngine,
    ProgressionAnalyzer,
    ConstraintChecker,
    ExerciseVariationSuggester
)


@click.group()
def cli():
    """
    Arnold - Expert Exercise System

    JUDGMENT-DAY: Your workout, decided.
    """
    pass


@cli.command()
@click.option('--date', 'date_str', type=str, help='Plan date (YYYY-MM-DD), default: tomorrow')
@click.option('--focus', type=str, help='Workout focus (e.g., "Upper Push")')
@click.option('--type', 'workout_type', type=str, default='strength', help='Workout type (strength/conditioning/skill)')
def plan(date_str: Optional[str], focus: Optional[str], workout_type: str):
    """Generate a workout plan."""
    graph = ArnoldGraph()

    if not graph.verify_connectivity():
        click.echo("❌ Could not connect to CYBERDYNE-CORE")
        return

    planner = WorkoutPlanner(graph)

    # Parse date
    if date_str:
        plan_date = date.fromisoformat(date_str)
    else:
        plan_date = date.today() + timedelta(days=1)

    try:
        workout_plan = planner.generate_daily_plan(
            plan_date=plan_date,
            focus=focus,
            workout_type=workout_type
        )

        # Format and display
        formatted = planner.format_plan_text(workout_plan)
        click.echo(formatted)

    except Exception as e:
        click.echo(f"❌ Error generating plan: {e}")
    finally:
        graph.close()


@cli.command()
def status():
    """Show current training status and periodization phase."""
    graph = ArnoldGraph()

    if not graph.verify_connectivity():
        click.echo("❌ Could not connect to CYBERDYNE-CORE")
        return

    try:
        periodization = PeriodizationEngine(graph)
        analytics = ProgressionAnalyzer(graph)

        # Get current phase
        phase, week, cycle_start = periodization.get_current_phase()
        phase_targets = periodization.get_phase_targets(phase)

        # Get summary stats
        stats = analytics.get_summary_stats(weeks=4)

        # Get adherence
        adherence = periodization.get_adherence_rate(weeks=4)

        # Check overtraining
        overtraining = analytics.detect_overtraining(weeks=4)

        click.echo("=" * 60)
        click.echo("ARNOLD TRAINING STATUS")
        click.echo("=" * 60)

        click.echo(f"\nCurrent Phase: {phase.value} (Week {week})")
        click.echo(f"Phase Focus: {phase_targets['focus']}")
        click.echo(f"Target Intensity: {int(phase_targets['intensity_range'][0]*100)}-{int(phase_targets['intensity_range'][1]*100)}%")
        click.echo(f"Target RPE: {phase_targets['rpe_range'][0]}-{phase_targets['rpe_range'][1]}")
        click.echo(f"Volume Multiplier: {int(phase_targets['volume_multiplier']*100)}%")

        click.echo(f"\n{'─' * 60}")
        click.echo("RECENT TRAINING (Last 4 Weeks)")
        click.echo('─' * 60)
        click.echo(f"Total Workouts: {stats.get('total_workouts', 0)}")
        click.echo(f"Total Sets: {stats.get('total_sets', 0)}")
        click.echo(f"Total Tonnage: {stats.get('total_tonnage', 0):,.0f} lbs")
        click.echo(f"Average RPE: {stats.get('avg_rpe', 0):.1f}" if stats.get('avg_rpe') else "Average RPE: N/A")
        click.echo(f"Adherence Rate: {adherence:.0f}%")

        click.echo(f"\n{'─' * 60}")
        click.echo("READINESS")
        click.echo('─' * 60)
        risk = overtraining['overtraining_risk']
        risk_color = 'green' if risk == 'low' else 'yellow' if risk == 'moderate' else 'red'
        click.echo(f"Overtraining Risk: ", nl=False)
        click.secho(risk.upper(), fg=risk_color)

        if overtraining.get('signals'):
            click.echo("\nSignals:")
            for signal in overtraining['signals']:
                click.echo(f"  ⚠  {signal}")

        click.echo(f"\nRecommendation: {overtraining['recommendation']}")

        click.echo("\n" + "=" * 60)

    except Exception as e:
        click.echo(f"❌ Error: {e}")
    finally:
        graph.close()


@cli.command()
@click.option('--exercise', required=True, help='Exercise name')
@click.option('--weeks', default=12, help='Number of weeks to analyze')
def analyze(exercise: str, weeks: int):
    """Analyze progression for an exercise."""
    graph = ArnoldGraph()

    if not graph.verify_connectivity():
        click.echo("❌ Could not connect to CYBERDYNE-CORE")
        return

    try:
        analyzer = ProgressionAnalyzer(graph)

        # Get progression data
        progression = analyzer.get_exercise_progression(exercise, weeks)

        if not progression:
            click.echo(f"❌ No data found for '{exercise}' in the last {weeks} weeks")
            return

        # Check stagnation
        stagnation = analyzer.detect_stagnation(exercise, weeks)

        click.echo("=" * 60)
        click.echo(f"PROGRESSION ANALYSIS: {exercise}")
        click.echo("=" * 60)

        # Show progression table
        click.echo(f"\nDate       | Weight | Reps | Sets | RPE | Est 1RM")
        click.echo("─" * 60)

        for p in progression:
            date_str = str(p['date'])
            weight = f"{p['weight']:.0f}" if p['weight'] else "N/A"
            reps = str(p['reps']) if p['reps'] else "N/A"
            sets = str(p['sets']) if p['sets'] else "N/A"
            rpe = f"{p['rpe']:.0f}" if p['rpe'] else "N/A"
            est_1rm = f"{p['estimated_1rm']:.0f}" if p['estimated_1rm'] else "N/A"

            click.echo(f"{date_str} | {weight:>6} | {reps:>4} | {sets:>4} | {rpe:>3} | {est_1rm:>7}")

        # Stagnation analysis
        click.echo(f"\n{'─' * 60}")
        click.echo("STAGNATION CHECK")
        click.echo('─' * 60)

        if stagnation['stagnant']:
            click.secho(f"⚠  STAGNANT", fg='yellow')
            click.echo(f"Reason: {stagnation['reason']}")
            click.echo(f"Recommendation: {stagnation['recommendation']}")
        else:
            click.secho(f"✓ PROGRESSING", fg='green')
            if stagnation.get('improvement_pct'):
                click.echo(f"Improvement: {stagnation['improvement_pct']:.1f}%")

        click.echo("\n" + "=" * 60)

    except Exception as e:
        click.echo(f"❌ Error: {e}")
    finally:
        graph.close()


@cli.command()
@click.option('--exercise', required=True, help='Exercise name')
@click.option('--reason', help='Reason for alternative (e.g., "knee pain")')
@click.option('--limit', default=5, help='Number of alternatives')
def alt(exercise: str, reason: Optional[str], limit: int):
    """Suggest alternative exercises."""
    graph = ArnoldGraph()

    if not graph.verify_connectivity():
        click.echo("❌ Could not connect to CYBERDYNE-CORE")
        return

    try:
        variation = ExerciseVariationSuggester(graph)

        # Get variations
        variations = variation.suggest_variations(exercise, limit=limit)

        if not variations:
            click.echo(f"❌ No alternatives found for '{exercise}'")
            return

        click.echo("=" * 60)
        click.echo(f"ALTERNATIVES FOR: {exercise}")
        if reason:
            click.echo(f"Reason: {reason}")
        click.echo("=" * 60)

        for i, v in enumerate(variations, 1):
            click.echo(f"\n{i}. {v['name']}")
            click.echo(f"   Equipment: {v.get('equipment', 'N/A')}")
            click.echo(f"   Level: {v.get('level', 'N/A')}")
            click.echo(f"   Muscles: {', '.join(v.get('muscles', []))}")
            click.echo(f"   Relevance: {v.get('relevance_score', 0):.1f}/10")

        click.echo("\n" + "=" * 60)

    except Exception as e:
        click.echo(f"❌ Error: {e}")
    finally:
        graph.close()


@cli.command()
@click.option('--weeks', default=4, help='Number of weeks to analyze')
@click.option('--by', 'group_by', type=click.Choice(['muscle', 'exercise']), default='muscle', help='Group by muscle or exercise')
def volume(weeks: int, group_by: str):
    """Show training volume breakdown."""
    graph = ArnoldGraph()

    if not graph.verify_connectivity():
        click.echo("❌ Could not connect to CYBERDYNE-CORE")
        return

    try:
        analyzer = ProgressionAnalyzer(graph)

        if group_by == 'muscle':
            # Muscle group balance
            balance = analyzer.get_muscle_group_balance(weeks)

            click.echo("=" * 60)
            click.echo(f"VOLUME BY MUSCLE GROUP (Last {weeks} weeks)")
            click.echo("=" * 60)

            if not balance:
                click.echo("\n❌ No volume data available")
                return

            # Sort by volume
            sorted_balance = sorted(balance.items(), key=lambda x: x[1], reverse=True)

            click.echo(f"\nMuscle Group          | Volume %")
            click.echo("─" * 60)

            for muscle, pct in sorted_balance:
                bar_length = int(pct / 2)  # Scale to fit terminal
                bar = "█" * bar_length
                click.echo(f"{muscle:20} | {pct:5.1f}% {bar}")

        else:  # by exercise
            # Volume trend
            trend = analyzer.get_volume_trend(weeks=weeks)

            click.echo("=" * 60)
            click.echo(f"WEEKLY VOLUME TREND (Last {weeks} weeks)")
            click.echo("=" * 60)

            if not trend:
                click.echo("\n❌ No volume data available")
                return

            click.echo(f"\nWeek       | Tonnage | Sets")
            click.echo("─" * 60)

            for t in trend:
                week_str = str(t['week'])
                tonnage = f"{t['tonnage']:,.0f}" if t['tonnage'] else "0"
                sets = str(t['sets']) if t['sets'] else "0"
                click.echo(f"{week_str} | {tonnage:>10} | {sets:>4}")

        click.echo("\n" + "=" * 60)

    except Exception as e:
        click.echo(f"❌ Error: {e}")
    finally:
        graph.close()


if __name__ == '__main__':
    cli()
