import type { ResearchEvent } from '@/lib/api'
import type { ResearchRun } from '@/components/research-trace'

const questions = [
  'What notable prediction did Augustin-Jean Fresnel make about the bright spot behind a circular obstacle?',
  'What constant value did Max Planck introduce in his blackbody radiation formula?',
  'What measurement about light-induced electron emission did Philipp Lenard report?',
  'Who proposed in 1905 that light consists of quanta with energy proportional to frequency?',
  'What year did Arthur Compton publish the X-ray scattering experiment showing a wavelength shift?',
  'What result do single-photon double-slit experiments demonstrate about interference patterns?',
  'Who first quantized the electromagnetic field in a formal theoretical treatment?'
]

function gap(id: number, status: 'resolved' | 'partial' | 'unresolved', missing: string[] = []): ResearchEvent {
  return { type: 'gap', id, question: questions[id - 1], status, missing }
}

const events: ResearchEvent[] = [
  { type: 'gaps', questions },
  {
    type: 'search',
    gap_id: 1,
    urls: [
      'https://en.wikipedia.org/wiki/Arago_spot',
      'https://plato.stanford.edu/entries/quantum-mechanics/',
      'https://www.nobelprize.org/prizes/physics/1921/summary/'
    ]
  },
  {
    type: 'finding',
    gap_id: 1,
    source: 'https://en.wikipedia.org/wiki/Arago_spot',
    answers: true,
    note: 'Fresnel predicted that a bright spot would appear at the center of the shadow behind a circular obstacle, because diffracted waves from the rim arrive there in phase.'
  },
  { type: 'dead_url', url: 'https://www.jstor.org/stable/10.2307/2278901' },
  {
    type: 'finding',
    gap_id: 4,
    source: 'https://www.nobelprize.org/prizes/physics/1921/summary/',
    answers: true,
    note: 'In 1905 Einstein proposed that light consists of quanta whose energy is proportional to frequency, E = hν.'
  },
  { type: 'dead_url', url: 'https://sci-hub.example/10.1103/physrev.21.483' },
  {
    type: 'finding',
    gap_id: 2,
    source: 'https://plato.stanford.edu/entries/quantum-mechanics/',
    answers: false,
    note: 'Planck introduced a constant to fit the blackbody curve, but this page does not quote the value he assigned.'
  },
  { type: 'dead_url', url: 'https://paywall.nature.com/articles/fresnel-1818' },
  { type: 'dead_url', url: 'https://cdn.journal.test/lenard/1902/electron-emission.pdf' },
  gap(1, 'resolved'),
  gap(2, 'partial', ['the numerical value of the constant']),
  gap(3, 'unresolved'),
  gap(4, 'resolved'),
  gap(5, 'partial', ['the publication year']),
  gap(6, 'unresolved'),
  gap(7, 'resolved'),
  {
    type: 'search',
    gap_id: 5,
    urls: ['https://history.aip.org/exhibits/gap/PDF/compton.pdf']
  },
  {
    type: 'finding',
    gap_id: 5,
    source: 'https://history.aip.org/exhibits/gap/PDF/compton.pdf',
    answers: true,
    note: 'Compton published the X-ray scattering result, with a wavelength shift that depended on the scattering angle, in 1923.'
  },
  { type: 'dead_url', url: 'https://www.jstor.org/stable/10.2307/2278901' },
  gap(1, 'resolved'),
  gap(2, 'partial', ['the numerical value of the constant']),
  gap(3, 'partial', ['the stopping voltage Lenard measured']),
  gap(4, 'resolved'),
  gap(5, 'resolved'),
  gap(6, 'unresolved'),
  gap(7, 'resolved')
]

export const tracePreviewRun: ResearchRun = {
  id: 'trace-preview',
  topic: 'Evolution of the theory of the dual nature of light',
  status: 'running',
  phase: 'researching',
  questions: [],
  reviewError: null,
  events,
  activity: 'Writing your report',
  error: null
}
