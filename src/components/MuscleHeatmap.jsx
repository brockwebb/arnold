import React, { useState, useMemo } from 'react';
import Model from 'react-body-highlighter';

/**
 * Mapping from Neo4j muscle names to react-body-highlighter muscle slugs
 * Package supports: trapezius, upper-back, lower-back, chest, biceps, triceps, 
 * forearm, back-deltoids, front-deltoids, abs, obliques, adductor, hamstring, 
 * quadriceps, abductors, calves, gluteal, head, neck
 */
const MUSCLE_TO_SLUG = {
  // Back
  'Trapezius': 'trapezius',
  'Trapezius (Upper)': 'trapezius',
  'Trapezius (Middle)': 'trapezius',
  'Trapezius (Lower)': 'trapezius',
  'Latissimus Dorsi': 'upper-back',
  'Rhomboids': 'upper-back',
  'Teres Major': 'upper-back',
  'Back': 'upper-back',
  'Erector Spinae': 'lower-back',
  'Quadratus Lumborum': 'lower-back',
  
  // Chest
  'Pectoralis Major': 'chest',
  'Pectoralis Minor': 'chest',
  'Serratus Anterior': 'chest',
  'Chest': 'chest',
  
  // Shoulders
  'Deltoid (Anterior)': 'front-deltoids',
  'Deltoid (Lateral)': 'front-deltoids',
  'Deltoid (Posterior)': 'back-deltoids',
  'Shoulders': 'front-deltoids',
  'Rotator Cuff': 'back-deltoids',
  'Infraspinatus': 'back-deltoids',
  'Supraspinatus': 'back-deltoids',
  'Subscapularis': 'back-deltoids',
  'Teres Minor': 'back-deltoids',
  
  // Arms
  'Biceps Brachii': 'biceps',
  'Brachialis': 'biceps',
  'Arms': 'biceps',
  'Triceps Brachii': 'triceps',
  'Forearm Flexors': 'forearm',
  'Forearm Extensors': 'forearm',
  'Forearms': 'forearm',
  
  // Core
  'Rectus Abdominis': 'abs',
  'Transverse Abdominis': 'abs',
  'Core': 'abs',
  'External Obliques': 'obliques',
  'Internal Obliques': 'obliques',
  
  // Glutes & Hips
  'Gluteus Maximus': 'gluteal',
  'Gluteus Medius': 'gluteal',
  'Gluteus Minimus': 'gluteal',
  'Glutes': 'gluteal',
  'Hip Adductors': 'adductor',
  'Iliopsoas': 'adductor', // closest match
  'Hip Abductors': 'abductors',
  'Tensor Fasciae Latae': 'abductors',
  
  // Legs
  'Quadriceps Femoris': 'quadriceps',
  'Rectus Femoris': 'quadriceps',
  'Vastus Lateralis': 'quadriceps',
  'Vastus Medialis': 'quadriceps',
  'Vastus Intermedius': 'quadriceps',
  'Legs': 'quadriceps',
  'Biceps Femoris': 'hamstring',
  'Semimembranosus': 'hamstring',
  'Semitendinosus': 'hamstring',
  'Hamstrings': 'hamstring',
  'Gastrocnemius': 'calves',
  'Soleus': 'calves',
  'Tibialis Anterior': 'calves',
};

/**
 * Aggregate Neo4j muscle data into react-body-highlighter format
 */
function aggregateToSlugs(muscleData) {
  const slugVolumes = {};
  
  Object.entries(muscleData).forEach(([muscle, volume]) => {
    const slug = MUSCLE_TO_SLUG[muscle];
    if (slug) {
      slugVolumes[slug] = (slugVolumes[slug] || 0) + volume;
    }
  });
  
  return slugVolumes;
}

/**
 * Convert aggregated volumes to frequency (1-5 scale for coloring)
 * Uses percentile-based bucketing within the data
 */
function volumeToFrequency(slugVolumes) {
  const volumes = Object.values(slugVolumes).filter(v => v > 0);
  if (volumes.length === 0) return {};
  
  volumes.sort((a, b) => a - b);
  const p20 = volumes[Math.floor(volumes.length * 0.2)] || 0;
  const p40 = volumes[Math.floor(volumes.length * 0.4)] || 0;
  const p60 = volumes[Math.floor(volumes.length * 0.6)] || 0;
  const p80 = volumes[Math.floor(volumes.length * 0.8)] || 0;
  
  const frequencies = {};
  Object.entries(slugVolumes).forEach(([slug, volume]) => {
    if (volume <= 0) frequencies[slug] = 0;
    else if (volume <= p20) frequencies[slug] = 1;
    else if (volume <= p40) frequencies[slug] = 2;
    else if (volume <= p60) frequencies[slug] = 3;
    else if (volume <= p80) frequencies[slug] = 4;
    else frequencies[slug] = 5;
  });
  
  return frequencies;
}

/**
 * Build data array for react-body-highlighter
 */
function buildModelData(slugFrequencies) {
  return Object.entries(slugFrequencies)
    .filter(([_, freq]) => freq > 0)
    .map(([slug, frequency]) => ({
      name: slug,
      muscles: [slug],
      frequency,
    }));
}

/**
 * MuscleHeatmap Component
 * 
 * Props:
 *   muscleData: Object mapping muscle names to volume (from Neo4j)
 *   title: Optional title string
 *   onMuscleClick: Optional callback (muscle, data) => void
 */
export default function MuscleHeatmap({ 
  muscleData = {}, 
  title = 'Muscle Heatmap',
  onMuscleClick 
}) {
  const [selectedMuscle, setSelectedMuscle] = useState(null);
  
  // Process data
  const slugVolumes = useMemo(() => aggregateToSlugs(muscleData), [muscleData]);
  const slugFrequencies = useMemo(() => volumeToFrequency(slugVolumes), [slugVolumes]);
  const modelData = useMemo(() => buildModelData(slugFrequencies), [slugFrequencies]);
  
  // Color scale: blue (low) -> cyan -> green -> yellow -> red (high)
  const highlightedColors = [
    '#3B82F6', // blue - frequency 1
    '#22D3EE', // cyan - frequency 2
    '#22C55E', // green - frequency 3
    '#FACC15', // yellow - frequency 4
    '#EF4444', // red - frequency 5
  ];
  
  const handleClick = ({ muscle, data }) => {
    setSelectedMuscle({ muscle, data, volume: slugVolumes[muscle] || 0 });
    onMuscleClick?.({ muscle, data, volume: slugVolumes[muscle] || 0 });
  };
  
  const formatVolume = (v) => {
    if (v >= 1000000) return (v / 1000000).toFixed(1) + 'M';
    if (v >= 1000) return (v / 1000).toFixed(0) + 'k';
    return v.toString();
  };
  
  return (
    <div className="muscle-heatmap">
      <h2 style={{ textAlign: 'center', marginBottom: '1rem' }}>{title}</h2>
      
      <div style={{ display: 'flex', justifyContent: 'center', gap: '2rem' }}>
        {/* Front view */}
        <div>
          <div style={{ textAlign: 'center', fontSize: '0.875rem', color: '#9CA3AF' }}>FRONT</div>
          <Model
            data={modelData}
            style={{ width: '12rem' }}
            highlightedColors={highlightedColors}
            onClick={handleClick}
            type="anterior"
          />
        </div>
        
        {/* Back view */}
        <div>
          <div style={{ textAlign: 'center', fontSize: '0.875rem', color: '#9CA3AF' }}>BACK</div>
          <Model
            data={modelData}
            style={{ width: '12rem' }}
            highlightedColors={highlightedColors}
            onClick={handleClick}
            type="posterior"
          />
        </div>
      </div>
      
      {/* Selected muscle info */}
      {selectedMuscle && (
        <div style={{ 
          textAlign: 'center', 
          marginTop: '1rem',
          padding: '1rem',
          backgroundColor: '#1F2937',
          borderRadius: '0.5rem'
        }}>
          <div style={{ fontWeight: 'bold', textTransform: 'capitalize' }}>
            {selectedMuscle.muscle.replace('-', ' ')}
          </div>
          <div style={{ color: '#9CA3AF' }}>
            Volume: {formatVolume(selectedMuscle.volume)} lbs
          </div>
        </div>
      )}
      
      {/* Color legend */}
      <div style={{ 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center',
        gap: '0.5rem',
        marginTop: '1rem',
        fontSize: '0.75rem',
        color: '#9CA3AF'
      }}>
        <span>Low</span>
        <div style={{
          height: '0.75rem',
          width: '8rem',
          borderRadius: '0.25rem',
          background: `linear-gradient(to right, ${highlightedColors.join(', ')})`
        }} />
        <span>High</span>
      </div>
    </div>
  );
}
