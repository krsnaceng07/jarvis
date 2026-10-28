attribute vec3 aPosA;
attribute vec3 aPosB;
attribute vec3 aColorA;
attribute vec3 aColorB;
attribute float aSeed;
attribute float aSize;

uniform float uTime;
uniform float uMix;
uniform float uDirection;
uniform float uPixelRatio;
uniform float uPointScale;
uniform float uFemaleOpacity;
uniform float uMaleOpacity;
uniform float uBurstStrength;
uniform float uSwirlStrength;
uniform float uSwirlBias;
uniform float uStreakWidth;
uniform float uStreakBrightness;
uniform float uScanY;
uniform float uScanActive;
uniform float uScanBandWidth;
uniform float uIdleJitter;
uniform float uSpeech;
uniform vec2 uMouthA;
uniform vec2 uMouthB;

varying vec3 vColor;
varying float vAlpha;
varying float vScan;

vec3 curlNoise(vec3 point) {
  float xy = cos(point.x + point.y);
  float yz = cos(point.y + point.z);
  float zx = cos(point.z + point.x);
  return vec3(xy - zx, yz - xy, zx - yz) * 0.5;
}

void main() {
  float progress = uDirection > 0.0 ? uMix : 1.0 - uMix;
  float delayed = clamp((progress - aSeed * 0.25) / 0.75, 0.0, 1.0);
  float sourceMix = uDirection > 0.0 ? delayed : 1.0 - delayed;
  vec3 base = mix(aPosA, aPosB, sourceMix);
  vec3 color = mix(aColorA, aColorB, sourceMix);

  float burst = sin(3.14159265 * progress);
  vec3 noisePoint = base * 1.5 + vec3(uTime * 0.4 + aSeed * 10.0);
  vec3 curl = curlNoise(noisePoint);
  float angle = burst * (uSwirlStrength * (aSeed - 0.5) + uSwirlBias);
  float cosine = cos(angle);
  float sine = sin(angle);
  vec2 rotated = vec2(base.x * cosine - base.y * sine, base.x * sine + base.y * cosine);
  vec2 swirl = rotated - base.xy;
  vec3 position = base + (curl * 0.9 + vec3(swirl, 0.0)) * burst * uBurstStrength;

  vec2 mouthAnchor = mix(uMouthA, uMouthB, sourceMix);
  float mouthShape = exp(-pow((base.x - mouthAnchor.x) / 0.065, 2.0) - pow((base.y - mouthAnchor.y) / 0.03, 2.0));
  float mouthOpen = clamp(uSpeech, 0.0, 1.0) * mouthShape;
  float lipSide = smoothstep(-0.008, 0.008, base.y - mouthAnchor.y) * 2.0 - 1.0;
  position.y += lipSide * mouthOpen * 0.018;
  position.x += (base.x - mouthAnchor.x) * mouthOpen * 0.08;

  position += vec3(
    sin(uTime * 2.7 + aSeed * 6.2831853),
    cos(uTime * 2.3 + aSeed * 6.2831853),
    sin(uTime * 3.1 + aSeed * 6.2831853)
  ) * uIdleJitter;

  float diagonal = dot(position.xy, normalize(vec2(1.0, 0.65)));
  float streakCenter = mix(-1.4, 1.4, progress);
  float streak = exp(-pow((diagonal - streakCenter) / uStreakWidth, 2.0)) * burst;
  color *= 1.0 + burst * 0.6 + streak * uStreakBrightness;
  color += vec3(0.12, 0.32, 0.58) * streak * uStreakBrightness;

  float scanDistance = abs(position.y - uScanY);
  float scan = uScanActive * (1.0 - smoothstep(uScanBandWidth * 0.65, uScanBandWidth, scanDistance));
  color = mix(color, vec3(0.96, 0.94, 0.66), scan);
  vColor = color;
  float opacity = mix(uFemaleOpacity, uMaleOpacity, uMix);
  vAlpha = opacity * (0.88 + 0.12 * sin(uTime * 2.4 + aSeed * 6.2831853)) * (1.0 + scan * 0.7 + streak * 0.35);
  vScan = scan;

  vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
  float attenuation = 2.8 / max(0.1, -viewPosition.z);
  float sizeBoost = 1.0 + burst * 0.6 + streak * 1.1 + scan * 0.75;
  gl_PointSize = clamp(aSize * attenuation * uPointScale * uPixelRatio * sizeBoost, 0.8 * uPixelRatio, 4.0 * uPixelRatio);
  gl_Position = projectionMatrix * viewPosition;
}
