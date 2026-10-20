<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, multipart, ok, sinSerializar } from '@/api/cliente'
import Alerta from '@/components/Alerta.vue'
import Estado from '@/components/Estado.vue'
import { usarAccion, usarCarga } from '@/utils/composables'
import { usd } from '@/utils/formato'

const props = defineProps<{ id: string }>()
const router = useRouter()
const path = computed(() => ({ params: { path: { estudio_id: Number(props.id) } } }))

const estudio = usarCarga(() => ok(api.GET('/paciente/estudios/{estudio_id}', path.value)))
const { datos: misCupones } = usarCarga(() => ok(api.GET('/paciente/cupones')))
const p = computed(() => estudio.datos.value?.presupuesto ?? null)
const puedePagar = computed(() => estudio.datos.value?.estado === 'POR_PAGAR' && p.value && !p.value.pagado)
const admiteCupon = computed(
  () => p.value && !p.value.cupon_codigo && p.value.modalidad !== 'OBRA_SOCIAL' && !p.value.pagado &&
    ['POR_PAGAR', 'PENDIENTE_AUTORIZACION'].includes(estudio.datos.value?.estado ?? ''),
)

// E9 Aplicar Cupón: por código o subiendo el PDF con el QR
const codigo = ref('')
const pdf = ref<File | null>(null)
const cupon = usarAccion()
async function aplicar(): Promise<void> {
  const r = await cupon.ejecutar(
    () =>
      ok(
        api.POST('/paciente/estudios/{estudio_id}/cupon', {
          ...path.value,
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          body: multipart({ codigo: codigo.value.trim(), archivo: pdf.value }) as any,
          ...sinSerializar,
        }),
      ),
    'Cupón aplicado.',
  )
  if (r) {
    codigo.value = ''
    pdf.value = null
    await estudio.recargar()
  }
}

// E8 Pagar (simulado, un solo pago)
const pago = usarAccion()
async function pagar(): Promise<void> {
  const r = await pago.ejecutar(() => ok(api.POST('/paciente/estudios/{estudio_id}/pagar', path.value)))
  if (r) await router.push(`/paciente/estudios/${props.id}?pagado=1`)
}
</script>

<template>
  <section class="pagina">
    <div class="encabezado">
      <div>
        <h1>Presupuesto</h1>
        <p>E8 y E9. El pago es simulado y en un solo pago.</p>
      </div>
      <RouterLink :to="`/paciente/estudios/${id}`" class="boton">Volver al Estudio</RouterLink>
    </div>
    <Estado :cargando="estudio.cargando.value" :error="estudio.error.value">
      <p v-if="!p" class="tarjeta vacio">El Laboratorio todavía no emitió el Presupuesto de este Estudio.</p>
      <template v-else>
        <div class="tarjeta">
          <dl>
            <div class="dato"><dt>Genes a analizar</dt><dd>{{ p.cantidad_genes }}</dd></div>
            <div class="dato"><dt>Monto del Estudio</dt><dd class="monto">{{ usd(p.monto_base_usd) }}</dd></div>
            <div v-if="p.obra_social" class="dato"><dt>Cobertura {{ p.obra_social }}</dt><dd class="monto">{{ p.cobertura_pct }}% · {{ usd(p.monto_obra_social_usd) }}</dd></div>
            <div v-if="p.cupon_codigo" class="dato"><dt>Cupón {{ p.cupon_codigo }}</dt><dd class="monto">-{{ usd(p.descuento_cupon_usd) }}</dd></div>
            <div class="dato total"><dt>Total a tu cargo</dt><dd class="monto">{{ usd(p.monto_a_pagar_usd) }}</dd></div>
          </dl>
          <Alerta v-if="estudio.datos.value?.estado === 'PENDIENTE_AUTORIZACION'" tipo="info">
            Tu Obra Social está evaluando el Estudio. Cuando lo autorice te avisamos
            {{ p.modalidad === 'MIXTA' ? 'y vas a poder pagar la diferencia' : 'y vas a poder sacar Turno' }}.
          </Alerta>
          <Alerta v-if="p.pagado" tipo="exito">El Presupuesto ya está pagado.</Alerta>
        </div>

        <form v-if="admiteCupon" class="tarjeta formulario" @submit.prevent="aplicar">
          <h2>Aplicar Cupón</h2>
          <p v-if="misCupones?.length" class="suave">
            Tenés {{ misCupones.length }} Cupón{{ misCupones.length > 1 ? 'es' : '' }}:
            <button v-for="c in misCupones" :key="c.id" type="button" class="boton boton--chico" @click="codigo = c.codigo">
              {{ c.codigo }} ({{ c.descuento_pct }}%)
            </button>
          </p>
          <div class="grilla-2">
            <label class="campo"><span>Código</span><input v-model="codigo" placeholder="LG20-XXXXXXXX" /></label>
            <label class="campo">
              <span>…o subí el PDF con el QR</span>
              <input type="file" accept="application/pdf" @change="pdf = ($event.target as HTMLInputElement).files?.[0] ?? null" />
            </label>
          </div>
          <Alerta v-if="cupon.error.value" tipo="error">{{ cupon.error.value }} El precio no cambió.</Alerta>
          <Alerta v-if="cupon.exito.value" tipo="exito">{{ cupon.exito.value }}</Alerta>
          <button class="boton" type="submit" :disabled="cupon.enCurso.value || (!codigo.trim() && !pdf)">Aplicar Cupón</button>
        </form>

        <div v-if="puedePagar" class="tarjeta formulario">
          <Alerta v-if="pago.error.value" tipo="error">{{ pago.error.value }}</Alerta>
          <button class="boton boton--primario" type="button" :disabled="pago.enCurso.value" @click="pagar">
            Pagar {{ usd(p.monto_a_pagar_usd) }}
          </button>
          <small class="suave">Pago simulado: no se debita dinero real.</small>
        </div>
      </template>
    </Estado>
  </section>
</template>

<style scoped>
.total dd { font-size: 1.15rem; }
</style>
