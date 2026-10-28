varying vec3 vColor;
varying float vAlpha;
varying float vScan;

void main() {
  float radius = length(gl_PointCoord - vec2(0.5));
  if (radius > 0.5) discard;
  float softEdge = 1.0 - smoothstep(0.24, 0.5, radius);
  float core = 1.0 - smoothstep(0.02, 0.34, radius);
  vec3 color = mix(vColor * 0.70, vColor, core);
  color += vec3(0.15, 0.35, 0.60) * vScan * core;
  // Holographic tone-mapping: prevents dense overlapping particles from blowing out into pure washed-out white
  color = color / (1.0 + color * 0.35);
  gl_FragColor = vec4(color, vAlpha * softEdge);
}
