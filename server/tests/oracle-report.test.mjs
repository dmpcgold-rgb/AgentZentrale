import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeBookingReport,readBookingReport} from '../oracle-report.mjs';
const sample={erstellt:'2026-01-01T07:00:00+01:00',dienst_status:'success',bereits_gebucht:['2026-01-02'],neu_gebucht:['2026-01-05'],gesamt_bestaetigt:2,lueckenlos_bis:'2026-01-05',offene_gepruefte_tage:[],fehler_oder_luecken:false};
test('only whitelisted fields exposed',()=>assert.deepEqual(normalizeBookingReport({...sample,token:'secret'}),sample));
test('reject inconsistent confirmation count',()=>assert.throws(()=>normalizeBookingReport({...sample,gesamt_bestaetigt:3})));
test('reject conflicting open dates',()=>assert.throws(()=>normalizeBookingReport({...sample,offene_gepruefte_tage:['2026-01-05']})));
test('unconfigured or missing file is not reported as successful',async()=>{assert.deepEqual(await readBookingReport(),{available:false,report:null});});
