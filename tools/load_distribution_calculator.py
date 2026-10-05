"""Cargo distribution calculator: /tools/raspredelenie-gruza-po-osyam/.

Given the cargo mass and where it lies in the semi-trailer body, the page
works out the loads on the tractor's front axle, its drive axle (or bogie)
and the semi-trailer bogie, checks them against the limits of Government
Decree No. 2060 (shared with the axle load calculator), and shows the range
of cargo centre positions where every axle stays within the limits.

Statics used (beam on two supports, lever rule):
  semi-trailer: supports are the kingpin and the bogie centre.
    cargo at distance x behind the kingpin, kingpin–bogie distance L:
      kingpin share = Q * (L - x) / L, bogie share = Q * x / L
  tractor: supports are the front axle and the rear axle (bogie centre).
    fifth wheel s metres ahead of the rear axle, wheelbase W:
      front share = P * s / W, rear share = P * (W - s) / W
Empty-vehicle axle loads are added on top. The math is plain JS
(DISTRIBUTION_JS) so it can be tested with node and run in the browser.
"""
from __future__ import annotations

import html
import json

from axle_calculator import AXLE_LIMITS, MASS_LIMITS, OFFICIAL_URL, ROAD_CLASSES, _page_css as _axle_css

PAGE_PATH = "/tools/raspredelenie-gruza-po-osyam/"

# Typical values; the page asks users to replace them with their own.
PRESETS = [
    {
        "id": "euro-4x2-3",
        "name": "Еврофура: тягач 4×2 + 3 оси",
        "tractor": {"rear": "single", "rearSpacing": "", "wheelbase": 3.7, "fifth": 0.6, "front0": 4.8, "rear0": 2.7},
        "trailer": {"group": "triple", "count": 3, "spacing": 1.31, "tyres": "single", "kingpinToBogie": 7.7,
                    "kingpinFromFront": 1.2, "body": 13.6, "kingpin0": 2.4, "bogie0": 4.4},
        "cargo": [{"mass": 20, "start": 0, "length": 13.6}],
    },
    {
        "id": "6x4-3",
        "name": "Тягач 6×4 + 3 оси",
        "tractor": {"rear": "double", "rearSpacing": 1.35, "wheelbase": 3.9, "fifth": 0.5, "front0": 5.3, "rear0": 4.0},
        "trailer": {"group": "triple", "count": 3, "spacing": 1.31, "tyres": "single", "kingpinToBogie": 7.0,
                    "kingpinFromFront": 1.2, "body": 12.0, "kingpin0": 2.8, "bogie0": 5.2},
        "cargo": [{"mass": 25, "start": 0, "length": 12}],
    },
    {
        "id": "6x4-4",
        "name": "7 осей: тягач 3 оси + полуприцеп 4 оси",
        "tractor": {"rear": "double", "rearSpacing": 1.35, "wheelbase": 3.9, "fifth": 0.5, "front0": 5.3, "rear0": 4.0},
        "trailer": {"group": "multi", "count": 4, "spacing": 1.36, "tyres": "single", "kingpinToBogie": 7.2,
                    "kingpinFromFront": 1.2, "body": 12.0, "kingpin0": 3.0, "bogie0": 6.4},
        "cargo": [{"mass": 25, "start": 0, "length": 12}],
    },
    {
        # Single truck: cargo rests on the chassis between the front axle and
        # the rear bogie; a loader crane (КМУ) is part of the empty weight.
        "id": "truck-6x4-kmu",
        "name": "Бортовой 6×4 с КМУ (КАМАЗ)",
        "kind": "truck",
        "tractor": {"rear": "double", "rearSpacing": 1.32, "wheelbase": 4.35, "fifth": 0, "front0": 6.0, "rear0": 6.5,
                    "bodyFromFront": 2.4, "truckBody": 6.1},
        "cargo": [{"mass": 7, "start": 0, "length": 6.1}],
    },
    {
        "id": "truck-6x4-dump",
        "name": "Самосвал 6×4",
        "kind": "truck",
        "tractor": {"rear": "double", "rearSpacing": 1.32, "wheelbase": 4.35, "fifth": 0, "front0": 5.4, "rear0": 5.0,
                    "bodyFromFront": 1.0, "truckBody": 5.1},
        "cargo": [{"mass": 13, "start": 0, "length": 5.1}],
    },
]

DISTRIBUTION_JS = r"""
function spacingBand(d){ if (d < 1) return 'lt1'; if (d < 1.3) return '1-1.3'; if (d < 1.8) return '1.3-1.8'; if (d <= 2.5) return '1.8-2.5'; return null; }

// Allowed load on an axle group (tonnes, whole group). road: index in [6, 10, 11.5].
function groupLimit(LIMITS, type, tyres, spacing, count, road){
  if (type === 'single') return LIMITS.single[tyres].any[road];
  const b = spacingBand(spacing); if (!b) return NaN;
  const v = LIMITS[type][tyres][b][road];
  return type === 'multi' ? v * count : v;
}

function cargoCentre(cargo){
  let m = 0, mx = 0;
  cargo.forEach(c => { m += c.mass; mx += c.mass * (c.start + c.length / 2); });
  return {mass: m, centre: m > 0 ? mx / m : 0};
}

// Loads on front axle, tractor rear axle/bogie, kingpin and trailer bogie.
// x — cargo centre measured from the front wall of the body.
// cfg.kind === 'truck': a single truck, the body starts bodyFromFront metres
// behind the front axle; the wheelbase runs to the rear axle (bogie centre).
function axleLoads(cfg, mass, x){
  const t = cfg.tractor, s = cfg.trailer;
  if (cfg.kind === 'truck'){
    const p = t.bodyFromFront + x, W = t.wheelbase;
    const front = t.front0 + mass * (W - p) / W, rear = t.rear0 + mass * p / W;
    return {front, rear, kingpin: 0, bogie: 0, total: front + rear};
  }
  const fromKingpin = x - s.kingpinFromFront;
  const L = s.kingpinToBogie;
  const kingpinCargo = mass * (L - fromKingpin) / L;
  const bogie = s.bogie0 + mass * fromKingpin / L;
  const kingpin = s.kingpin0 + kingpinCargo;
  const front = t.front0 + kingpin * t.fifth / t.wheelbase;
  const rear = t.rear0 + kingpin * (t.wheelbase - t.fifth) / t.wheelbase;
  return {front, rear, kingpin, bogie, total: front + rear + bogie};
}

function limitsFor(cfg, LIMITS, road){
  const t = cfg.tractor, s = cfg.trailer;
  return {
    front: groupLimit(LIMITS, 'single', 'single', 0, 1, road),
    rear: groupLimit(LIMITS, t.rear, 'dual', t.rearSpacing, 2, road),
    bogie: cfg.kind === 'truck' ? Infinity : groupLimit(LIMITS, s.group, s.tyres, s.spacing, s.count, road),
  };
}

function axleCount(cfg){
  if (cfg.kind === 'truck') return 1 + (cfg.tractor.rear === 'single' ? 1 : 2);
  return 1 + (cfg.tractor.rear === 'single' ? 1 : 2) + (cfg.trailer.group === 'double' ? 2 : cfg.trailer.group === 'triple' ? 3 : cfg.trailer.count);
}

function massLimit(MASS, axles, kind){
  const table = MASS[kind === 'truck' ? 'truck' : 'train']; const keys = Object.keys(table).map(Number).sort((a,b) => a-b);
  if (axles < keys[0]) return NaN;
  return table[keys.filter(k => k <= axles).pop()];
}

// Range of cargo centre positions (from the front wall) where every axle
// group is within its limit; best = position with the largest smallest margin.
function safeRange(cfg, LIMITS, road, mass){
  const lim = limitsFor(cfg, LIMITS, road);
  const body = cfg.kind === 'truck' ? cfg.tractor.truckBody : cfg.trailer.body, step = 0.05;
  let from = null, to = null, best = null, bestMargin = -Infinity;
  for (let i = 0; i <= Math.round(body / step); i++){
    const x = i * step;
    const l = axleLoads(cfg, mass, x);
    const margin = Math.min(lim.front - l.front, lim.rear - l.rear, lim.bogie - l.bogie);
    if (margin >= -1e-9){ if (from === null) from = x; to = x; }
    if (margin > bestMargin){ bestMargin = margin; best = x; }
  }
  return {from, to, best, bestMargin};
}
"""


FAQ = [
    (
        "Как рассчитать нагрузку на оси тягача и полуприцепа?",
        "Груз в полуприцепе опирается на две точки: шкворень (через седло — на тягач) и тележку полуприцепа. "
        "Чем ближе центр груза к тележке, тем больше нагрузка на тележку и меньше — на седло. Нагрузку на седло тягач делит "
        "между передней и задней осью: чем ближе седло к задней оси, тем больше достаётся ей. Калькулятор считает это по правилу рычага.",
    ),
    (
        "Почему при нормальной общей массе перегружена ось тягача?",
        "Если груз сдвинут к передней стенке, на шкворень приходится больше веса, и ведущая ось тягача получает лишние тонны. "
        "Общая масса при этом может быть в норме — штраф выписывают за перегруз оси.",
    ),
    (
        "Сколько можно загрузить в еврофуру?",
        "Тягач 4×2 с трёхосным полуприцепом — это пятиосный автопоезд, допустимая масса 40 т. Грузоподъёмность — это 40 т минус масса "
        "тягача и полуприцепа (обычно 14–15 т), то есть около 25 т. Но и при этом груз нужно разместить так, чтобы ни одна ось не была перегружена.",
    ),
    (
        "Какая допустимая масса семиосного автопоезда?",
        "Для автопоезда с шестью и более осями допустимая масса — 44 т. Седьмая ось не увеличивает предел массы, "
        "но снижает нагрузку на каждую ось.",
    ),
    (
        "Как распределится груз на грузовике с КМУ?",
        "Кран-манипулятор стоит за кабиной и уже нагружает переднюю ось и тележку — его масса входит в массу пустого автомобиля. "
        "Груз в кузове делится между передней осью и задней тележкой по правилу рычага: если центр груза за задней тележкой, "
        "тележка перегружается, а передняя ось разгружается. Выберите в калькуляторе «Грузовик» и укажите, где начинается кузов.",
    ),
    (
        "Где взять размеры для расчёта?",
        "Колёсную базу, вынос седла и нагрузки на оси без груза смотрите в документах производителя или взвесьте пустой автопоезд по осям. "
        "Расстояние от шкворня до центра тележки и до передней стенки можно измерить рулеткой.",
    ),
]


def _page_css() -> str:
    return _axle_css() + """
.dist-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:12px}
.dist-cargo{display:grid;grid-template-columns:repeat(3,minmax(0,1fr)) auto;gap:10px;align-items:end;margin-top:10px}
.dist-sub{margin:20px 0 4px;font-size:16px;font-weight:800}
.dist-scheme{margin-top:16px;width:100%;height:auto;display:block}
.dist-range{margin-top:12px;padding:14px 16px;border-radius:12px;background:var(--bg);font-size:15px;line-height:1.5}
@media (max-width:760px){ .dist-grid{grid-template-columns:1fr 1fr} .dist-cargo{grid-template-columns:1fr 1fr} }
"""


def _page_js() -> str:
    return DISTRIBUTION_JS + r"""
(function(){
  const D = JSON.parse(document.getElementById('dist-data').textContent);
  const $ = s => document.querySelector(s);
  const num = v => { const x = parseFloat(String(v).replace(',', '.')); return isFinite(x) ? x : NaN; };
  const fmt = n => (Math.round(n*100)/100).toLocaleString('ru-RU');
  const cargoEl = $('#dist-cargo');
  const F = ['wheelbase','fifth','front0','rear0','rearSpacing','bodyFromFront','truckBody','spacing','count','kingpinToBogie','kingpinFromFront','body','kingpin0','bogie0'];
  function cargoRow(c){
    const el = document.createElement('div'); el.className = 'dist-cargo';
    el.innerHTML = '<label class="calc-field">Масса груза, т<input data-k="mass" inputmode="decimal"></label>' +
      '<label class="calc-field">От передней стенки, м<input data-k="start" inputmode="decimal"></label>' +
      '<label class="calc-field">Длина груза, м<input data-k="length" inputmode="decimal"></label>' +
      '<button type="button" class="calc-remove" aria-label="Удалить">×</button>';
    ['mass','start','length'].forEach(k => el.querySelector('[data-k='+k+']').value = String(c[k]).replace('.', ','));
    el.addEventListener('input', calc);
    el.querySelector('.calc-remove').addEventListener('click', () => { el.remove(); calc(); });
    cargoEl.appendChild(el);
  }
  function load(p){
    $('#d-kind').value = p.kind || 'train';
    $('#t-rear').value = p.tractor.rear;
    if (p.trailer) { $('#s-group').value = p.trailer.group; $('#s-tyres').value = p.trailer.tyres; }
    F.forEach(k => { const el = $('#f-'+k); if (!el) return; const v = k in p.tractor ? p.tractor[k] : (p.trailer || {})[k]; if (v !== undefined) el.value = String(v).replace('.', ','); });
    cargoEl.innerHTML = ''; p.cargo.forEach(cargoRow); calc();
  }
  function read(){
    const v = k => num($('#f-'+k).value);
    const rear = $('#t-rear').value, group = $('#s-group').value;
    return {
      kind: $('#d-kind').value,
      tractor: {rear, rearSpacing: v('rearSpacing'), wheelbase: v('wheelbase'), fifth: v('fifth'), front0: v('front0'), rear0: v('rear0'), bodyFromFront: v('bodyFromFront'), truckBody: v('truckBody')},
      trailer: {group, count: group === 'multi' ? Math.max(4, Math.round(v('count')) || 4) : (group === 'double' ? 2 : 3), spacing: v('spacing'), tyres: $('#s-tyres').value,
        kingpinToBogie: v('kingpinToBogie'), kingpinFromFront: v('kingpinFromFront'), body: v('body'), kingpin0: v('kingpin0'), bogie0: v('bogie0')},
      cargo: [...cargoEl.querySelectorAll('.dist-cargo')].map(el => ({mass: num(el.querySelector('[data-k=mass]').value), start: num(el.querySelector('[data-k=start]').value), length: num(el.querySelector('[data-k=length]').value)})),
    };
  }
  function cell(name, fact, limit){
    const bad = isFinite(limit) && fact > limit + 1e-9;
    const diff = limit - fact;
    return '<tr><td>' + name + '</td><td><b>' + fmt(fact) + ' т</b></td><td>' + (isFinite(limit) ? fmt(limit) + ' т' : '—') + '</td><td class="' + (bad ? 'calc-bad' : 'calc-ok') + '">' +
      (!isFinite(limit) ? '' : bad ? 'перегруз ' + fmt(-diff) + ' т (' + fmt(-diff / limit * 100) + '%)' : 'запас ' + fmt(diff) + ' т') + '</td></tr>';
  }
  function calc(){
    $('#f-rearSpacing').closest('label').style.display = $('#t-rear').value === 'single' ? 'none' : '';
    $('#f-count').closest('label').style.display = $('#s-group').value === 'multi' ? '' : 'none';
    const truck = $('#d-kind').value === 'truck';
    document.querySelectorAll('[data-only=train]').forEach(e => e.style.display = truck ? 'none' : '');
    document.querySelectorAll('[data-only=truck]').forEach(e => e.style.display = truck ? '' : 'none');
    $('#f-fifth').closest('label').style.display = truck ? 'none' : '';
    $('#f-bodyFromFront').closest('label').style.display = truck ? '' : 'none';
    $('#f-truckBody').closest('label').style.display = truck ? '' : 'none';
    const cfg = read(); const road = D.roads.indexOf(num($('#calc-road').value));
    const out = $('#dist-result'), verdict = $('#calc-verdict'), range = $('#dist-range');
    const vals = truck
      ? [cfg.tractor.wheelbase, cfg.tractor.front0, cfg.tractor.rear0, cfg.tractor.bodyFromFront, cfg.tractor.truckBody]
      : [cfg.tractor.wheelbase, cfg.tractor.fifth, cfg.tractor.front0, cfg.tractor.rear0, cfg.trailer.kingpinToBogie, cfg.trailer.kingpinFromFront, cfg.trailer.body, cfg.trailer.kingpin0, cfg.trailer.bogie0];
    const cargoOk = cfg.cargo.length && cfg.cargo.every(c => isFinite(c.mass) && isFinite(c.start) && isFinite(c.length));
    if (vals.some(v => !isFinite(v)) || !cargoOk) { out.innerHTML = ''; range.textContent = ''; verdict.className = 'calc-verdict'; verdict.textContent = 'Заполните все поля.'; return; }
    const bodyLen = truck ? cfg.tractor.truckBody : cfg.trailer.body;
    const outside = cfg.cargo.some(c => c.start < 0 || c.start + c.length > bodyLen + 1e-9);
    const {mass, centre} = cargoCentre(cfg.cargo);
    const l = axleLoads(cfg, mass, centre), lim = limitsFor(cfg, D.limits, road);
    const axles = axleCount(cfg), mLim = massLimit(D.mass, axles, cfg.kind);
    const who = truck ? 'автомобиля' : 'тягача';
    out.innerHTML = '<table class="calc-table"><thead><tr><th>Ось</th><th>Нагрузка</th><th>Допустимо</th><th></th></tr></thead><tbody>' +
      cell('Передняя ось ' + who, l.front, lim.front) +
      cell(cfg.tractor.rear === 'single' ? 'Задняя ось ' + who : 'Задняя тележка ' + who + ' (2 оси)', l.rear, lim.rear) +
      (truck ? '' : cell('Тележка полуприцепа (' + cfg.trailer.count + ' ' + (cfg.trailer.count > 4 ? 'осей' : 'оси') + ')', l.bogie, lim.bogie)) +
      cell((truck ? 'Автомобиль целиком (' : 'Автопоезд целиком (') + axles + (axles > 4 ? ' осей)' : ' оси)'), l.total, mLim) +
      '</tbody></table><p class="calc-note">' + (truck ? '' : 'Нагрузка на седло (шкворень): ' + fmt(l.kingpin) + ' т. ') + 'Центр груза — ' + fmt(centre) + ' м от передней стенки кузова, масса груза ' + fmt(mass) + ' т.' +
      (truck && l.front < 0.2 * l.total ? ' <b>На переднюю ось приходится меньше 20 % массы</b> — управляемость ухудшается, сдвиньте груз вперёд.' : '') + '</p>';
    const over = [l.front > lim.front, l.rear > lim.rear, l.bogie > lim.bogie].filter(Boolean).length;
    const massBad = isFinite(mLim) && l.total > mLim + 1e-9;
    if (outside) { verdict.className = 'calc-verdict bad'; verdict.textContent = 'Груз выходит за пределы кузова — проверьте начало и длину.'; }
    else if (over || massBad) { verdict.className = 'calc-verdict bad'; verdict.textContent = [over ? 'Перегружено групп осей: ' + over : '', massBad ? 'масса больше допустимой на ' + fmt(l.total - mLim) + ' т' : ''].filter(Boolean).join('; ') + '. Переставьте груз или уменьшите его массу, иначе нужно спецразрешение.'; }
    else { verdict.className = 'calc-verdict ok'; verdict.textContent = 'Все оси и общая масса в пределах нормы для выбранной дороги.'; }
    const r = safeRange(cfg, D.limits, road, mass);
    if (r.from === null) range.innerHTML = '<b>Такую массу груза не разместить без перегруза ни в одном положении</b> — для выбранной дороги её нужно уменьшить. Наименьший перегруз — если центр груза в ' + fmt(r.best) + ' м от передней стенки.';
    else range.innerHTML = 'Чтобы ни одна ось не была перегружена, центр груза массой ' + fmt(mass) + ' т должен быть <b>от ' + fmt(r.from) + ' до ' + fmt(r.to) + ' м</b> от передней стенки. Лучше всего — около <b>' + fmt(r.best) + ' м</b>' + (massBad ? ', но общая масса всё равно больше допустимой.' : '.');
    drawScheme(cfg, centre, r);
  }
  function drawScheme(cfg, centre, r){
    const svg = $('#dist-scheme'); const s = cfg.trailer, t = cfg.tractor;
    if (cfg.kind === 'truck'){
      const W = 720, pad = 20, total = 1.2 + Math.max(t.wheelbase + 1.5, t.bodyFromFront + t.truckBody) + 0.3, k = (W - 2*pad) / total;
      const frontX = pad + 1.2 * k, rearX = frontX + t.wheelbase * k, bodyX = frontX + t.bodyFromFront * k, cx = bodyX + centre * k;
      let g = '<rect x="'+pad+'" y="30" width="'+(2.2*k)+'" height="56" rx="6" fill="var(--ink)" opacity=".85"/>';
      g += '<rect x="'+pad+'" y="82" width="'+(Math.max(rearX + 0.9*k, bodyX + t.truckBody*k) - pad)+'" height="6" fill="var(--ink)" opacity=".85"/>';
      g += '<rect x="'+bodyX+'" y="40" width="'+(t.truckBody*k)+'" height="38" rx="3" fill="none" stroke="var(--ink)" stroke-width="2"/>';
      if (r.from !== null) g += '<rect x="'+(bodyX + r.from*k)+'" y="40" width="'+Math.max(2,(r.to - r.from)*k)+'" height="38" fill="#1d7a3a" opacity=".18"/>';
      [frontX, rearX].forEach(x => g += '<circle cx="'+x+'" cy="98" r="11" fill="var(--ink)"/>');
      g += '<line x1="'+cx+'" y1="22" x2="'+cx+'" y2="80" stroke="#ff6b00" stroke-width="3"/><text x="'+cx+'" y="18" text-anchor="middle" font-size="12" fill="#ff6b00" font-weight="700">центр груза</text>';
      g += '<text x="'+frontX+'" y="126" text-anchor="middle" font-size="11" fill="currentColor">перед. ось</text><text x="'+rearX+'" y="126" text-anchor="middle" font-size="11" fill="currentColor">задняя ось / тележка</text>';
      svg.innerHTML = g; return;
    }
    const W = 720, pad = 20, total = t.wheelbase + 1.5 + s.body; const k = (W - 2*pad) / total;
    const rearX = pad + (1.2 + t.wheelbase) * k, fifthX = rearX - t.fifth * k, frontX = pad + 1.2 * k;
    const bodyX = fifthX - s.kingpinFromFront * k, bogieX = fifthX + s.kingpinToBogie * k;
    const cx = bodyX + centre * k;
    let g = '<rect x="'+pad+'" y="40" width="'+(1.9*k)+'" height="46" rx="6" fill="var(--ink)" opacity=".85"/>';
    g += '<rect x="'+pad+'" y="82" width="'+(rearX + 0.8*k - pad)+'" height="6" fill="var(--ink)" opacity=".85"/>';
    g += '<rect x="'+(fifthX - 0.4*k)+'" y="76" width="'+(0.8*k)+'" height="6" fill="#ff6b00"/>';
    g += '<rect x="'+bodyX+'" y="22" width="'+(s.body*k)+'" height="52" rx="4" fill="none" stroke="var(--ink)" stroke-width="2"/>';
    if (r.from !== null) g += '<rect x="'+(bodyX + r.from*k)+'" y="22" width="'+Math.max(2,(r.to - r.from)*k)+'" height="52" fill="#1d7a3a" opacity=".18"/>';
    [frontX, rearX, bogieX].forEach(x => g += '<circle cx="'+x+'" cy="98" r="11" fill="var(--ink)"/>');
    g += '<line x1="'+cx+'" y1="10" x2="'+cx+'" y2="80" stroke="#ff6b00" stroke-width="3"/><text x="'+cx+'" y="8" text-anchor="middle" font-size="12" fill="#ff6b00" font-weight="700">центр груза</text>';
    g += '<text x="'+frontX+'" y="126" text-anchor="middle" font-size="11" fill="currentColor">перед. ось</text><text x="'+rearX+'" y="126" text-anchor="middle" font-size="11" fill="currentColor">зад. ось</text><text x="'+bogieX+'" y="126" text-anchor="middle" font-size="11" fill="currentColor">тележка</text>';
    svg.innerHTML = g;
  }
  document.querySelectorAll('[data-preset]').forEach(b => b.addEventListener('click', () => load(D.presets.find(p => p.id === b.dataset.preset))));
  $('#dist-add').addEventListener('click', () => { cargoRow({mass: 5, start: 0, length: 2.4}); calc(); });
  document.querySelectorAll('#dist-form input, #dist-form select').forEach(el => { el.addEventListener('input', calc); el.addEventListener('change', calc); });
  $('#f-bodyFromFront').value = '2,4'; $('#f-truckBody').value = '6,1';
  load(D.presets[0]);
})();
"""


def _field(key: str, label: str) -> str:
    return f'<label class="calc-field">{html.escape(label)}<input id="f-{key}" inputmode="decimal"></label>'


def render_distribution_calculator_page(base_url: str, telegram_cta: str) -> str:
    canonical = base_url + PAGE_PATH
    title = "Расчёт нагрузки на оси тягача и полуприцепа — калькулятор распределения груза"
    description = (
        "Бесплатный калькулятор: как распределится груз по осям тягача и полуприцепа или грузовика с КМУ, где разместить груз без перегруза. "
        "Еврофура, семиосный автопоезд, самосвал; нормы по ПП № 2060."
    )[:200]
    data = {
        "roads": ROAD_CLASSES,
        "limits": AXLE_LIMITS,
        "mass": {k: {str(n): v for n, v in table.items()} for k, table in MASS_LIMITS.items()},
        "presets": PRESETS,
    }
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    presets_html = "".join(
        f'<button type="button" data-preset="{html.escape(p["id"], quote=True)}">{html.escape(p["name"])}</button>' for p in PRESETS
    )
    faq_html = "".join(
        f'<details class="regulation-faq__item"><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>' for q, a in FAQ
    )
    schema = json.dumps(
        [
            {
                "@context": "https://schema.org",
                "@type": "WebApplication",
                "name": "Калькулятор распределения груза по осям тягача и полуприцепа",
                "url": canonical,
                "applicationCategory": "BusinessApplication",
                "operatingSystem": "Any",
                "inLanguage": "ru-RU",
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "RUB"},
                "isBasedOn": OFFICIAL_URL,
            },
            {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in FAQ
                ],
            },
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    tractor_fields = "".join(_field(k, l) for k, l in (
        ("wheelbase", "Колёсная база, м"),
        ("bodyFromFront", "Кузов начинается за передней осью, м"),
        ("truckBody", "Длина кузова, м"),
        ("fifth", "Седло впереди задней оси, м"),
        ("rearSpacing", "Между осями тележки, м"),
        ("front0", "Пустой: на переднюю ось, т"),
        ("rear0", "Пустой: на заднюю ось, т"),
    ))
    trailer_fields = "".join(_field(k, l) for k, l in (
        ("spacing", "Между осями тележки, м"),
        ("count", "Осей в тележке"),
        ("kingpinToBogie", "Шкворень → центр тележки, м"),
        ("kingpinFromFront", "Шкворень от передней стенки, м"),
        ("body", "Длина кузова, м"),
        ("kingpin0", "Пустой: на шкворень, т"),
        ("bogie0", "Пустой: на тележку, т"),
    ))
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)} | СпецАвтоПортал</title>
  <meta name="description" content="{html.escape(description, quote=True)}" />
  <meta name="robots" content="index,follow,max-image-preview:large" />
  <link rel="canonical" href="{canonical}" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="СпецАвтоПортал" />
  <meta property="og:title" content="{html.escape(title, quote=True)}" />
  <meta property="og:description" content="{html.escape(description, quote=True)}" />
  <meta property="og:url" content="{canonical}" />
  <link rel="stylesheet" href="/styles.css?v=30" />
  <link rel="icon" href="/spec_avtoportal_favicon.ico" type="image/x-icon" />
  <script type="application/ld+json">{schema}</script>
  <style>{_page_css()}</style>
</head>
<body class="regulation-page">
  <div class="topline"><div class="container topline-inner"><span>Профессиональное медиа о грузовой технике</span><span class="topline-dot"></span><span>Инструменты</span></div></div>
  <header class="site-header">
    <div class="container header-inner">
      <a href="/" class="brand" aria-label="СпецАвтоПортал — на главную">
        <span class="brand-mark" aria-hidden="true"><span></span><span></span></span>
        <span class="brand-copy"><strong>СпецАвтоПортал</strong><small>рынок · техника · регламенты</small></span>
      </a>
      <nav class="main-nav" aria-label="Основная навигация">
        <a href="/" class="nav-link">Новости</a>
        <a href="/brands/" class="nav-link">Бренды</a>
        <a href="/knowledge.html" class="nav-link">База знаний</a>
        <a href="/tools/nagruzka-na-os/" class="nav-link nav-link-active">Калькулятор</a>
      </nav>
      <div class="header-socials" aria-label="Социальные сети">
        <a href="https://t.me/specavtoportal" class="header-social-link header-social-link--telegram" target="_blank" rel="noopener" aria-label="Telegram"><span class="social-full">Telegram</span><span class="social-short">TG</span></a>
        <a href="https://vk.ru/specavtoportal" class="header-social-link" target="_blank" rel="noopener" aria-label="VK"><span class="social-full">VK</span><span class="social-short">VK</span></a>
      </div>
    </div>
  </header>

  <main>
    <section class="regulation-hero">
      <div class="container">
        <p class="section-kicker"><a href="/knowledge.html">База знаний</a> · Инструменты</p>
        <h1>Распределение груза по осям тягача и полуприцепа</h1>
        <p class="regulation-hero__title">Укажите массу груза и где он лежит в кузове — калькулятор посчитает нагрузку на каждую ось и покажет, куда поставить груз, чтобы не было перегруза.</p>
      </div>
    </section>

    <section class="container regulation-layout">
      <article class="regulation-main">
        <section class="calc-card" id="dist-form">
          <p class="section-kicker">Расчёт</p>
          <h2>Ваш автопоезд</h2>
          <div class="calc-row">
            <label class="calc-field">Дорога рассчитана на
              <select id="calc-road"><option value="6">6 т на ось</option><option value="10" selected>10 т на ось</option><option value="11.5">11,5 т на ось</option></select>
            </label>
          </div>
          <p class="calc-note">Типовая схема — затем замените размеры и массы на данные своей техники:</p>
          <div class="calc-presets">{presets_html}</div>

          <div class="calc-row" style="margin-top:14px"><label class="calc-field">Что считаем
            <select id="d-kind"><option value="train">Тягач с полуприцепом</option><option value="truck">Грузовик: бортовой, с КМУ, самосвал</option></select></label></div>

          <p class="dist-sub"><span data-only="train">Тягач</span><span data-only="truck">Автомобиль</span></p>
          <div class="calc-row"><label class="calc-field">Задние оси
            <select id="t-rear"><option value="single">Одна ось (4×2)</option><option value="double">Две оси (6×4, 6×2)</option></select></label></div>
          <div class="dist-grid">{tractor_fields}</div>

          <p class="calc-note" data-only="truck">Колёсная база — от передней оси до задней оси или до центра задней тележки. Массу пустого автомобиля указывайте вместе с краном-манипулятором и кузовом.</p>
          <div data-only="train">
          <p class="dist-sub">Полуприцеп</p>
          <div class="calc-row">
            <label class="calc-field">Тележка
              <select id="s-group"><option value="double">2 оси</option><option value="triple">3 оси</option><option value="multi">4 и больше осей</option></select></label>
            <label class="calc-field">Колёса тележки
              <select id="s-tyres"><option value="single">Односкатные</option><option value="dual">Двускатные</option></select></label>
          </div>
          <div class="dist-grid">{trailer_fields}</div>
          </div>

          <p class="dist-sub">Груз</p>
          <div id="dist-cargo"></div>
          <button type="button" class="calc-add" id="dist-add" style="margin-top:12px">+ Добавить груз</button>

          <svg id="dist-scheme" class="dist-scheme" viewBox="0 0 720 132" role="img" aria-label="Схема автопоезда: оси, кузов и центр груза; зелёным — допустимая зона центра груза"></svg>
          <div id="dist-result" class="calc-scroll" style="margin-top:8px"></div>
          <div class="calc-verdict" id="calc-verdict" aria-live="polite">Заполните данные.</div>
          <div class="dist-range" id="dist-range" aria-live="polite"></div>
          <p class="calc-note">Расстояния — в метрах, массы — в тоннах. Для сдвоенной оси тягача колёсная база и вынос седла считаются до центра тележки. Груз, лежащий равномерно, задайте одной строкой с началом и длиной; несколько партий — отдельными строками.</p>
        </section>

        <section class="regulation-section">
          <p class="section-kicker">Как это работает</p>
          <h2>Почему важно, где лежит груз</h2>
          <p>Полуприцеп опирается на две точки: шкворень, который стоит на седле тягача, и свою тележку. Груз делится между ними по правилу рычага: чем ближе центр груза к тележке, тем больше достаётся ей и меньше — седлу.</p>
          <p>Нагрузку на седло тягач делит между передней и задней осью. Седло обычно стоит немного впереди задней оси, поэтому основная часть нагрузки уходит на ведущую ось. Отсюда типичная ситуация: груз сдвинули к передней стенке — и перегружена ведущая ось тягача, хотя общая масса в норме.</p>
          <ol>
            <li>Выберите типовую схему и замените размеры и массы на свои — из документов производителя или по результатам взвешивания пустого автопоезда по осям.</li>
            <li>Задайте груз: массу, где он начинается от передней стенки и какую длину занимает.</li>
            <li>Посмотрите нагрузки по осям и зелёную зону на схеме — в её пределах должен оказаться центр груза.</li>
          </ol>
        </section>

        {telegram_cta}

        <section class="regulation-section regulation-faq">
          <p class="section-kicker">Вопросы и ответы</p>
          <h2>Частые вопросы</h2>
          {faq_html}
        </section>

        <section class="regulation-section">
          <p class="section-kicker">По теме</p>
          <h2>Что почитать</h2>
          <ul>
            <li><a href="/tools/nagruzka-na-os/">Калькулятор нагрузки на ось — если нагрузки по осям уже известны</a></li>
            <li><a href="/knowledge/nagruzka-na-osi-evrofury/">Нагрузка на оси еврофуры и семиосного автопоезда</a></li>
            <li><a href="/knowledge/shtraf-za-peregruz/">Штраф за перегруз в 2026 году</a></li>
            <li><a href="/tools/skolko-pallet-v-furu/">Сколько паллет поместится в фуру</a></li>
            <li><a href="/knowledge/kreplenie-gruzov/">Крепление грузов в полуприцепе</a></li>
            <li><a href="/knowledge/specrazreshenie-tyazhelovesnoe-ts/">Спецразрешение на тяжеловесный транспорт</a></li>
          </ul>
        </section>
      </article>

      <aside class="regulation-sidebar">
        <section class="sidebar-block sidebar-dark">
          <p class="sidebar-eyebrow">Нормы</p>
          <h3>Постановление Правительства РФ № 2060 от 01.12.2023</h3>
          <p class="sidebar-text">Допустимые нагрузки на оси и масса — приложения 2 и 3 к Правилам движения тяжеловесного и крупногабаритного транспорта.</p>
          <a class="partner-card__button" href="{OFFICIAL_URL}" target="_blank" rel="noopener">Открыть официальный документ <span>↗</span></a>
        </section>
        <section class="sidebar-block">
          <p class="sidebar-eyebrow">Важно</p>
          <p class="sidebar-text">Расчёт справочный: он не учитывает уклон, торможение и точность исходных данных. Перед рейсом проверяйте нагрузки взвешиванием.</p>
        </section>
      </aside>
    </section>
  </main>

  <footer class="site-footer">
    <div class="container footer-grid">
      <div><a href="/" class="footer-brand">СпецАвтоПортал</a><p>Отраслевое медиа о прицепах, полуприцепах и грузовой технике.</p></div>
      <div class="footer-nav"><a href="/knowledge.html">База знаний</a><a href="/law.html">Нормативы</a><a href="/tools/nagruzka-na-os/">Калькулятор нагрузки</a><a href="{PAGE_PATH}">Распределение груза</a><a href="/brands/">Бренды</a><a href="https://t.me/specavtoportal" target="_blank" rel="noopener">Telegram ↗</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
  <script type="application/json" id="dist-data">{data_json}</script>
  <script>{_page_js()}</script>
</body>
</html>
"""
