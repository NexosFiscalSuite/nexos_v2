import { useEffect, useRef } from 'react'
import * as THREE from 'three'

/**
 * Shader WebGL adaptado (do original shadcn/TS) para o nosso stack Vite/JSX:
 * - preenche o CONTAINER pai (absolute inset:0), não a viewport;
 * - paleta tingida de VERDE NEXOS (em vez do arco-íris) p/ casar com o card navy;
 * - respeita prefers-reduced-motion e pausa quando a aba está oculta (bateria/CPU).
 *
 * Use sobre um fundo escuro com `mix-blend-mode: screen` para virar "linhas de luz".
 */
export function ShaderAnimation() {
  const containerRef = useRef(null)
  const ref = useRef(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const vertexShader = `
      void main() { gl_Position = vec4( position, 1.0 ); }
    `
    // Mesma matemática do original; só o COR final é tingido de verde Nexos.
    const fragmentShader = `
      precision highp float;
      uniform vec2 resolution;
      uniform float time;
      void main(void) {
        vec2 uv = (gl_FragCoord.xy * 2.0 - resolution.xy) / min(resolution.x, resolution.y);
        float t = time * 0.05;
        float lineWidth = 0.002;
        vec3 color = vec3(0.0);
        for(int j = 0; j < 3; j++){
          for(int i = 0; i < 5; i++){
            color[j] += lineWidth * float(i*i) / abs(fract(t - 0.01*float(j) + float(i)*0.01)*5.0 - length(uv) + mod(uv.x+uv.y, 0.2));
          }
        }
        vec3 tint = vec3(0.30, 1.0, 0.55);   // #82DF6F-ish (verde Nexos)
        gl_FragColor = vec4(color * tint, 1.0);
      }
    `

    const camera = new THREE.Camera()
    camera.position.z = 1
    const scene = new THREE.Scene()
    const geometry = new THREE.PlaneGeometry(2, 2)
    const uniforms = {
      time: { value: 1.0 },
      resolution: { value: new THREE.Vector2() },
    }
    const material = new THREE.ShaderMaterial({ uniforms, vertexShader, fragmentShader })
    scene.add(new THREE.Mesh(geometry, material))

    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    container.appendChild(renderer.domElement)

    const onResize = () => {
      const w = container.clientWidth || 1
      const h = container.clientHeight || 1
      renderer.setSize(w, h)
      uniforms.resolution.value.set(renderer.domElement.width, renderer.domElement.height)
    }
    onResize()
    window.addEventListener('resize', onResize)

    const reduz = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
    ref.current = { renderer, geometry, material, raf: 0, parado: false }

    const animate = () => {
      ref.current.raf = requestAnimationFrame(animate)
      uniforms.time.value += 0.05
      renderer.render(scene, camera)
    }
    if (reduz) {
      renderer.render(scene, camera)   // 1 frame estático (acessibilidade)
    } else {
      animate()
    }

    // Pausa a animação quando a aba não está visível.
    const onVis = () => {
      if (reduz) return
      if (document.hidden) {
        cancelAnimationFrame(ref.current.raf)
      } else {
        animate()
      }
    }
    document.addEventListener('visibilitychange', onVis)

    return () => {
      window.removeEventListener('resize', onResize)
      document.removeEventListener('visibilitychange', onVis)
      cancelAnimationFrame(ref.current.raf)
      if (renderer.domElement.parentNode === container) container.removeChild(renderer.domElement)
      renderer.dispose()
      geometry.dispose()
      material.dispose()
    }
  }, [])

  return <div ref={containerRef} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', overflow: 'hidden' }} />
}

export default ShaderAnimation
