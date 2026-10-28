# 本地源码证据摘录（原始行号）

## /home/private/project-301/engine-stable/src/cpp/cdm/PhysiologyEngineThunk.cpp
```cpp
268: bool PhysiologyEngineThunk::ProcessActions(std::string const& actions, eSerializationFormat format)
269: {
270:   bool success = true;
271:   if (actions.empty())
272:     return success;
273: 
274:   try
275:   {
276:     std::vector<SEAction*> vActions;
277:     if (!SEActionManager::SerializeFromString(actions, vActions, format, m_engine->GetSubstanceManager()))
278:       return false;
279: 
280:     for (const SEAction* a : vActions)
281:     {
282:       if (!m_engine->ProcessAction(*a))
283:         success = false;
284:       delete a;
285:     }
286:   }
287:   catch (CommonDataModelException& ex)
288:   {
289:     success = false;
290:     m_engine->GetLogger()->Error(ex.what());
291:   }
292:   catch (std::exception& ex)
293:   {
294:     success = false;
295:     m_engine->GetLogger()->Error(ex.what());
296:   }
297:   catch (...)
298:   {
299:     success = false;
300:   }
301: 
302:   return success;
303: }
304: std::string PhysiologyEngineThunk::PullActiveActions(eSerializationFormat format)
305: {
306:   std::string stream;
307:   m_engine->GetActionManager().SerializeToString(stream, format);
308:   return stream;
309: }
```

## /home/private/project-301/engine-stable/src/cpp/cdm/engine/SEActionManager.cpp
```cpp
71: bool SEActionManager::ProcessAction(const SEAction& action)
72: {
73:   if (!action.IsValid())
74:   {
75:     m_ss << "Ignoring invalid action : " << action;
76:     Error(m_ss);
77:     return false;
78:   }
79:   bool bRet = true;
80: 
81:   const SEPatientAction* pa = dynamic_cast<const SEPatientAction*>(&action);
82:   if (pa != nullptr)
83:     bRet = m_PatientActions->ProcessAction(*pa);
84: 
85:   const SEEnvironmentAction* ea = dynamic_cast<const SEEnvironmentAction*>(&action);
86:   if (ea != nullptr)
87:     bRet = m_EnvironmentActions->ProcessAction(*ea);
88: 
89:   const SEEquipmentAction* ia = dynamic_cast<const SEEquipmentAction*>(&action);
90:   if (ia != nullptr)
91:     bRet = m_EquipmentActions->ProcessAction(*ia);
92: 
93:   if (!bRet)
94:   {
95:     m_ss << "Not including action due to processing error : " << action;
96:     Error(m_ss);
97:   }
98:   return bRet;
99: }
100: 
```

## /home/private/project-301/engine-stable/src/cpp/cdm/engine/SEPatientActionCollection.cpp
```cpp
193: bool SEPatientActionCollection::ProcessAction(const SEPatientAction& action)
194: {
195:   const SEPatientAssessmentRequest* patientAss = dynamic_cast<const SEPatientAssessmentRequest*>(&action);
196:   if (patientAss != nullptr)
197:   {
198:     // TODO just add this to a list?
199:     // Not doing anything with this, assessment actions
200:     // are currently only being handled by the Engine ScenarioExec methods.
201:     // Which probably just write out the assessment requested to a file
202:     // Assessments are really a real time API thing, not really a scenario thing
203:     // If they are a scenario thing, its just to write out the data.
204:     return true;//?
205:   }
206: 
207:   // We are creating our own copy of these actions
208:   // There can be multiple actions in a Scenario that are associated
209:   // with a specific function, such as hemorrhage, and we only need
210:   // to have a single action in our list associated with a hemorrhage.
211:   // We just overwrite our saved action with the current state of that action
212:   // So if the 4 hemorrhage actions come in, and lower the rate each time for a
213:   // certain compartment, we just update the single hemorrhage action associated
214:   // with that compartment.
215:   // SO, we make our own copy and manage that copy (i.e. by updating a single action)
216: 
217:   const SEAcuteRespiratoryDistressSyndromeExacerbation* ards = dynamic_cast<const SEAcuteRespiratoryDistressSyndromeExacerbation*>(&action);
218:   if (ards != nullptr)
```
```cpp
298:   if (cprCompression != nullptr)
299:   {
300:     if (HasChestCompressionInstantaneous())
301:     {
302:       Warning("Replacing active ChestCompressionInstantaneous action with this ChestCompression action");
303:     }
304:     if (HasChestCompression())
305:     {
306:       Warning("Current ChestCompression action has not completed, starting a new compression");
307:     }
308:     if (HasChestCompressionAutomated())
309:     {
310:       Warning("Replacing active ChestCompressionAutomated action with this ChestCompression action");
311:     }
312:     RemoveChestCompressionAutomated();
313:     RemoveChestCompressionInstantaneous();
314:     GetChestCompression().Copy(*cprCompression, true);
315:     m_ChestCompression->Activate();
316:     if (!m_ChestCompression->IsActive())
317:       RemoveChestCompression();
318:     return true;
319:   }
320: 
321:   const SEChestCompressionAutomated* cprAutomated = dynamic_cast<const SEChestCompressionAutomated*>(&action);
322:   if (cprAutomated != nullptr)
323:   {
324:     if (HasChestCompression())
325:     {
326:       Warning("Replacing active ChestCompression action with this ChestCompressionAutomated action");
327:     }
328:     if (HasChestCompressionInstantaneous())
329:     {
330:       Warning("Replacing active ChestCompressionInstantaneous action with this ChestCompressionAutomated action");
331:     }
332:     RemoveChestCompression();
333:     RemoveChestCompressionInstantaneous();
334:     GetChestCompressionAutomated().Copy(*cprAutomated, true);
335:     m_ChestCompressionAutomated->Activate();
336:     if (!m_ChestCompressionAutomated->IsActive())
337:       RemoveChestCompressionAutomated();
338:     return true;
339:   }
340: 
341:   const SEChestCompressionInstantaneous* cprInstantaneous = dynamic_cast<const SEChestCompressionInstantaneous*>(&action);
342:   if (cprInstantaneous != nullptr)
343:   {
344:     if (HasChestCompression())
345:     {
346:       Warning("Replacing active ChestCompression action with this ChestCompressionInstantaneous action");
347:     }
348:     if (HasChestCompressionAutomated())
349:     {
350:       Warning("Replacing active ChestCompressionAutomated action with this ChestCompressionInstantaneous action");
351:     }
352:     RemoveChestCompression();
353:     RemoveChestCompressionAutomated();
354:     GetChestCompressionInstantaneous().Copy(*cprInstantaneous, true);
355:     m_ChestCompressionInstantaneous->Activate();
356:     if (!m_ChestCompressionInstantaneous->IsActive())
357:       RemoveChestCompressionInstantaneous();
358:     return true;
359:   }
360: 
361:   const SEChestOcclusiveDressing* chestOccl = dynamic_cast<const SEChestOcclusiveDressing*>(&action);
362:   if (chestOccl != nullptr)
363:   {
364:     if (chestOccl->GetSide() == eSide::Left)
365:     {
366:       GetLeftChestOcclusiveDressing().Copy(*chestOccl, true);
367:       m_LeftChestOcclusiveDressing->Activate();
368:       if (!m_LeftChestOcclusiveDressing->IsActive())
369:         RemoveLeftChestOcclusiveDressing();
370:       return true;
371:     }
372:     else if (chestOccl->GetSide() == eSide::Right)
373:     {
374:       GetRightChestOcclusiveDressing().Copy(*chestOccl, true);
375:       m_RightChestOcclusiveDressing->Activate();
376:       if (!m_RightChestOcclusiveDressing->IsActive())
377:         RemoveRightChestOcclusiveDressing();
378:       return true;
379:     }
380:   }
381: 
382:   const SEChronicObstructivePulmonaryDiseaseExacerbation* copd = dynamic_cast<const SEChronicObstructivePulmonaryDiseaseExacerbation*>(&action);
383:   if (copd != nullptr)
384:   {
385:     GetChronicObstructivePulmonaryDiseaseExacerbation().Copy(*copd, true);
```
```cpp
438:   if (hem != nullptr)
439:   {
440:     SEHemorrhage& mine = GetHemorrhage(hem->GetCompartment());
441:     mine.Copy(*hem, true);
442:     mine.Activate();
443:     if (!mine.IsActive())
444:       RemoveHemorrhage(hem->GetCompartment());
445:     return true;
446:   }
447: 
448:   const SEHemothorax* hemo = dynamic_cast<const SEHemothorax*>(&action);
449:   if (hemo != nullptr)
450:   {
451:     if (hemo->GetSide() == eSide::Left)
452:     {
453:       GetLeftHemothorax().Copy(*hemo, true);
454:       m_LeftHemothorax->Activate();
455:       if (!m_LeftHemothorax->IsActive())
456:         RemoveLeftHemothorax();
457:       return true;
458:     }
459:     else if (hemo->GetSide() == eSide::Right)
460:     {
461:       GetRightHemothorax().Copy(*hemo, true);
462:       m_RightHemothorax->Activate();
463:       if (!m_RightHemothorax->IsActive())
464:         RemoveRightHemothorax();
465:       return true;
466:     }
467:     Error("Unknown Hemothorax Type");
468:     return false;// Duno what this is...
469:   }
470: 
471:   const SEImpairedAlveolarExchangeExacerbation* imaee = dynamic_cast<const SEImpairedAlveolarExchangeExacerbation*>(&action);
472:   if (imaee != nullptr)
473:   {
474:     GetImpairedAlveolarExchangeExacerbation().Copy(*imaee, true);
475:     m_ImpairedAlveolarExchangeExacerbation->Activate();
476:     if (!m_ImpairedAlveolarExchangeExacerbation->IsActive())
477:       RemoveImpairedAlveolarExchangeExacerbation();
478:     return true;
479:   }
480: 
481:   const SEIntubation* intubation = dynamic_cast<const SEIntubation*>(&action);
482:   if (intubation != nullptr)
483:   {
484:     GetIntubation().Copy(*intubation, true);
485:     m_Intubation->Activate();
486:     if (!m_Intubation->IsActive())
487:       RemoveIntubation();
488:     return true;
489:   }
490: 
```
```cpp
584:   const SESubstanceBolus* bolus = dynamic_cast<const SESubstanceBolus*>(&action);
585:   if (bolus != nullptr)
586:   {
587:     const SESubstance* sub = m_SubMgr.GetSubstance(bolus->GetSubstance().GetName());
588:     if (sub == nullptr)//Make sure this substance manager has it
589:     {
590:       Error("Ignoring SESubstanceBolus action due to unknown substance in action: " + bolus->GetSubstance().GetName());
591:       return false;
592:     }
593:     SESubstanceBolus& mine = GetSubstanceBolus(*sub);
594:     mine.Copy(*bolus, true);
595:     mine.Activate();
596:     if (!mine.IsActive())
597:       RemoveSubstanceBolus(*sub);
598:     else
599:       m_SubMgr.AddActiveSubstance(*sub);
600:     return true;
601:   }
602: 
603:   const SESubstanceInfusion* subInfusion = dynamic_cast<const SESubstanceInfusion*>(&action);
604:   if (subInfusion != nullptr)
605:   {
606:     const SESubstance* sub = m_SubMgr.GetSubstance(subInfusion->GetSubstance().GetName());
607:     if (sub == nullptr)//Make sure this substance manager has it
608:     {
609:       Error("Ignoring SESubstanceInfusion action due to unknown substance in action: " + subInfusion->GetSubstance().GetName());
610:       return false;
611:     }
612:     SESubstanceInfusion& mine = GetSubstanceInfusion(*sub);
613:     mine.Copy(*subInfusion, true);
614:     mine.Activate();
615:     if (!mine.IsActive())
616:       RemoveSubstanceInfusion(*sub);
617:     else
618:       m_SubMgr.AddActiveSubstance(*sub);
619:     return true;
620:   }
621: 
622:   const SESubstanceCompoundInfusion* cSubInfusion = dynamic_cast<const SESubstanceCompoundInfusion*>(&action);
623:   if (cSubInfusion != nullptr)
624:   {
625:     const SESubstanceCompound* cmpd = m_SubMgr.GetCompound(cSubInfusion->GetSubstanceCompound().GetName());
626:     if (cmpd == nullptr)//Make sure this substance manager has it
627:     {
628:       Error("Ignoring SESubstanceCompoundInfusion action due to unknown substance in action: " + cSubInfusion->GetSubstanceCompound().GetName());
629:       return false;
630:     }
631:     SESubstanceCompoundInfusion& mine = GetSubstanceCompoundInfusion(*cmpd);
632:     mine.Copy(*cSubInfusion, true);
633:     mine.Activate();
634:     if (!mine.IsActive())
635:       RemoveSubstanceCompoundInfusion(*cmpd);
636:     else
637:     {
638:       m_SubMgr.AddActiveCompound(*cmpd);
639:       for (const SESubstanceConcentration* scc : cmpd->GetComponents())
640:       {
641:         m_SubMgr.AddActiveSubstance(scc->GetSubstance());
642:       }
643:     }
644:     return true;
645:   }
646: 
647:   const SESupplementalOxygen* supplementalO2 = dynamic_cast<const SESupplementalOxygen*>(&action);
648:   if (supplementalO2 != nullptr)
649:   {
650:     GetSupplementalOxygen().Copy(*supplementalO2, true);
651:     m_SupplementalOxygen->Activate();
652:     if (!m_SupplementalOxygen->IsActive())
653:       RemoveSupplementalOxygen();
654:     return true;
655:   }
656: 
657:   const SETensionPneumothorax* pneumo = dynamic_cast<const SETensionPneumothorax*>(&action);
658:   if (pneumo != nullptr)
659:   {
660:     if (pneumo->GetSide() == eSide::Left&&pneumo->GetType() == eGate::Open)
661:     {
662:       GetLeftOpenTensionPneumothorax().Copy(*pneumo, true);
663:       m_LeftOpenTensionPneumothorax->Activate();
664:       if (!m_LeftOpenTensionPneumothorax->IsActive())
665:         RemoveLeftOpenTensionPneumothorax();
666:       return true;
667:     }
668:     else if (pneumo->GetSide() == eSide::Left&&pneumo->GetType() == eGate::Closed)
669:     {
670:       GetLeftClosedTensionPneumothorax().Copy(*pneumo, true);
```
```cpp
1436: bool SEPatientActionCollection::HasSubstanceBolus() const
1437: {
1438:   for (auto h : m_SubstanceBoluses)
1439:     if (h->IsActive())
1440:       return true;
1441:   return false;
1442: }
1443: bool SEPatientActionCollection::HasSubstanceBolus(const SESubstance& sub) const
1444: {
1445:   return GetSubstanceBolus(sub) != nullptr;
1446: }
1447: SESubstanceBolus& SEPatientActionCollection::GetSubstanceBolus(const SESubstance& sub)
1448: {
1449:   for (auto b : m_SubstanceBoluses)
1450:     if (&b->GetSubstance() == &sub)
1451:       return *b;
1452:   SESubstanceBolus* b = new SESubstanceBolus(sub, GetLogger());
1453:   m_SubstanceBoluses.push_back(b);
1454:   return *b;
1455: }
1456: const SESubstanceBolus* SEPatientActionCollection::GetSubstanceBolus(const SESubstance& sub) const
1457: {
1458:   for (auto b : m_SubstanceBoluses)
1459:     if (&b->GetSubstance() == &sub)
1460:       return b;
1461:   return nullptr;
1462: }
1463: const std::vector<SESubstanceBolus*>& SEPatientActionCollection::GetSubstanceBoluses()
1464: {
1465:   return m_SubstanceBoluses;
1466: }
1467: const std::vector<const SESubstanceBolus*> SEPatientActionCollection::GetSubstanceBoluses() const
1468: {
1469:   return std::vector<const SESubstanceBolus*>(m_SubstanceBoluses.begin(), m_SubstanceBoluses.end());
1470: }
1471: void SEPatientActionCollection::RemoveSubstanceBolus(const SESubstance& sub)
1472: {
1473:   GetSubstanceBolus(sub).Deactivate();
1474: }
1475: 
1476: bool SEPatientActionCollection::HasSubstanceInfusion() const
1477: {
1478:   for (auto h : m_SubstanceInfusions)
1479:     if (h->IsActive())
1480:       return true;
1481:   return false;
1482: }
1483: bool SEPatientActionCollection::HasSubstanceInfusion(const SESubstance& sub) const
1484: {
1485:   return GetSubstanceInfusion(sub) != nullptr;
1486: }
1487: SESubstanceInfusion& SEPatientActionCollection::GetSubstanceInfusion(const SESubstance& sub)
1488: {
1489:   for (auto si : m_SubstanceInfusions)
1490:     if (&si->GetSubstance() == &sub)
1491:       return *si;
1492:   SESubstanceInfusion* si = new SESubstanceInfusion(sub, GetLogger());
1493:   m_SubstanceInfusions.push_back(si);
1494:   return *si;
1495: }
1496: const SESubstanceInfusion* SEPatientActionCollection::GetSubstanceInfusion(const SESubstance& sub) const
1497: {
1498:   for (auto si : m_SubstanceInfusions)
1499:     if (&si->GetSubstance() == &sub)
1500:       return si;
1501:   return nullptr;
1502: }
1503: const std::vector<SESubstanceInfusion*>& SEPatientActionCollection::GetSubstanceInfusions()
1504: {
1505:   return m_SubstanceInfusions;
1506: }
1507: const std::vector<const SESubstanceInfusion*> SEPatientActionCollection::GetSubstanceInfusions() const
1508: {
1509:   return std::vector<const SESubstanceInfusion*>(m_SubstanceInfusions.begin(), m_SubstanceInfusions.end());
1510: }
1511: void SEPatientActionCollection::RemoveSubstanceInfusion(const SESubstance& sub)
1512: {
1513:   GetSubstanceInfusion(sub).Deactivate();
1514: }
1515: 
```

## /home/private/project-301/engine-stable/src/cpp/cdm/engine/SEEquipmentActionCollection.cpp
```cpp
121: bool SEEquipmentActionCollection::ProcessAction(const SEEquipmentAction& action)
122: {
123:   const SEMechanicalVentilatorAction* mva = dynamic_cast<const SEMechanicalVentilatorAction*>(&action);
124:   if (mva != nullptr)
125:   {
126:     // NOTE Ventilator mode actions are translated into the ventilator configuration action
127:     // So any new mode will need to be handled the same way and Removes, ToConfiguration calls
128:     // will need to be peppered through out this insides of this if block. Just follow the pattern
129:     // All ventilator actions are removed when the ventilator is turned off
130: 
131:     const SEMechanicalVentilatorConfiguration* config = dynamic_cast<const SEMechanicalVentilatorConfiguration*>(&action);
132:     if (config != nullptr)
133:     {
134:       GetMechanicalVentilatorConfiguration().Copy(*config, m_SubMgr, true);
135:       m_MechanicalVentilatorConfiguration->Activate();
136:       if (!m_MechanicalVentilatorConfiguration->IsActive())
137:         RemoveMechanicalVentilatorConfiguration();
138:       return true;
139:     }
140: 
141:     const SEMechanicalVentilatorHold* hold = dynamic_cast<const SEMechanicalVentilatorHold*>(&action);
142:     if (hold != nullptr)
143:     {
144:       GetMechanicalVentilatorHold().Copy(*hold, true);
145:       m_MechanicalVentilatorHold->Activate();
146:       if (!m_MechanicalVentilatorHold->IsActive())
147:         RemoveMechanicalVentilatorHold();
148:       return true;
149:     }
150: 
151:     const SEMechanicalVentilatorLeak* leak = dynamic_cast<const SEMechanicalVentilatorLeak*>(&action);
152:     if (leak != nullptr)
153:     {
154:       GetMechanicalVentilatorLeak().Copy(*leak, true);
155:       m_MechanicalVentilatorLeak->Activate();
156:       if (!m_MechanicalVentilatorLeak->IsActive())
157:         RemoveMechanicalVentilatorLeak();
158:       return true;
159:     }
160: 
161:     const SEMechanicalVentilatorContinuousPositiveAirwayPressure* cpap = dynamic_cast<const SEMechanicalVentilatorContinuousPositiveAirwayPressure*>(&action);
162:     if (cpap != nullptr)
163:     {
164:       GetMechanicalVentilatorContinuousPositiveAirwayPressure().Copy(*cpap, m_SubMgr, true);
165:       m_MechanicalVentilatorContinuousPositiveAirwayPressure->Activate();
166:       if (!m_MechanicalVentilatorContinuousPositiveAirwayPressure->IsActive())
167:         RemoveMechanicalVentilatorContinuousPositiveAirwayPressure();
168:       {
169:         RemoveMechanicalVentilatorPressureControl();
170:         RemoveMechanicalVentilatorVolumeControl();
171:         // Convert to a SEMechanicalVentilatorConfiguration
172:         GetMechanicalVentilatorConfiguration().Clear();
173:         GetMechanicalVentilatorConfiguration().SetMergeType(eMergeType::Replace);
174:         if (!GetMechanicalVentilatorContinuousPositiveAirwayPressure().ToSettings(GetMechanicalVentilatorConfiguration().GetSettings(), m_SubMgr))
175:         {
176:           RemoveMechanicalVentilatorContinuousPositiveAirwayPressure();
177:           GetMechanicalVentilatorConfiguration().Clear();
178:           Error("Ignoring invalid SEMechanicalVentilatorContinuousPositiveAirwayPressure action");
179:         }
180:         else
181:           m_MechanicalVentilatorConfiguration->Activate();
182:       }
183:       return true;
184:     }
185: 
186:     const SEMechanicalVentilatorPressureControl* pc = dynamic_cast<const SEMechanicalVentilatorPressureControl*>(&action);
187:     if (pc != nullptr)
188:     {
189:       GetMechanicalVentilatorPressureControl().Copy(*pc, m_SubMgr, true);
190:       m_MechanicalVentilatorPressureControl->Activate();
191:       if (!m_MechanicalVentilatorPressureControl->IsActive())
192:         RemoveMechanicalVentilatorPressureControl();
193:       {
194:         RemoveMechanicalVentilatorContinuousPositiveAirwayPressure();
195:         RemoveMechanicalVentilatorVolumeControl();
196:         // Convert to a SEMechanicalVentilatorConfiguration
197:         GetMechanicalVentilatorConfiguration().Clear();
198:         GetMechanicalVentilatorConfiguration().SetMergeType(eMergeType::Replace);
199:         if (!GetMechanicalVentilatorPressureControl().ToSettings(GetMechanicalVentilatorConfiguration().GetSettings(), m_SubMgr))
200:         {
201:           RemoveMechanicalVentilatorPressureControl();
202:           GetMechanicalVentilatorConfiguration().Clear();
203:           Error("Ignoring invalid SEMechanicalVentilatorPressureControl action");
204:         }
205:         else
206:           m_MechanicalVentilatorConfiguration->Activate();
207:       }
208:       return true;
209:     }
210: 
211:     const SEMechanicalVentilatorVolumeControl* vc = dynamic_cast<const SEMechanicalVentilatorVolumeControl*>(&action);
212:     if (vc != nullptr)
213:     {
214:       GetMechanicalVentilatorVolumeControl().Copy(*vc, m_SubMgr, true);
215:       m_MechanicalVentilatorVolumeControl->Activate();
216:       if (!m_MechanicalVentilatorVolumeControl->IsActive())
217:         RemoveMechanicalVentilatorVolumeControl();
218:       {
219:         RemoveMechanicalVentilatorContinuousPositiveAirwayPressure();
220:         RemoveMechanicalVentilatorPressureControl();
221:         // Convert to a SEMechanicalVentilatorConfiguration
222:         GetMechanicalVentilatorConfiguration().Clear();
223:         GetMechanicalVentilatorConfiguration().SetMergeType(eMergeType::Replace);
224:         if (!GetMechanicalVentilatorVolumeControl().ToSettings(GetMechanicalVentilatorConfiguration().GetSettings(), m_SubMgr))
225:         {
226:           RemoveMechanicalVentilatorVolumeControl();
227:           GetMechanicalVentilatorConfiguration().Clear();
228:           Error("Ignoring invalid SEMechanicalVentilatorVolumeControl action");
229:         }
230:         else
231:           m_MechanicalVentilatorConfiguration->Activate();
232:       }
233:       return true;
234:     }
235:   }
236: 
237:   const SEBagValveMaskAction* bvm = dynamic_cast<const SEBagValveMaskAction*>(&action);
238:   if (bvm != nullptr)
239:   {
240:     const SEBagValveMaskConfiguration* config = dynamic_cast<const SEBagValveMaskConfiguration*>(&action);
241:     if (config != nullptr)
242:     {
243:       GetBagValveMaskConfiguration().Copy(*config, m_SubMgr, true);
244:       m_BagValveMaskConfiguration->Activate();
245:       if (!m_BagValveMaskConfiguration->IsActive())
246:         RemoveBagValveMaskConfiguration();
247:       return true;
248:     }
249: 
250:     const SEBagValveMaskAutomated* automated = dynamic_cast<const SEBagValveMaskAutomated*>(&action);
251:     if (automated != nullptr)
252:     {
253:       if (HasBagValveMaskSqueeze())
254:       {
255:         Warning("Replacing active BagValveMaskSqueeze action with this BagValveMaskAutomated action");
256:       }
257:       if (HasBagValveMaskInstantaneous())
258:       {
259:         Warning("Replacing active BagValveMaskInstantaneous action with this BagValveMaskAutomated action");
260:       }
261:       RemoveBagValveMaskSqueeze();
262:       RemoveBagValveMaskInstantaneous();
263:       GetBagValveMaskAutomated().Copy(*automated);
264:       m_BagValveMaskAutomated->Activate();
265:       if (!m_BagValveMaskAutomated->IsActive())
266:         RemoveBagValveMaskAutomated();
267:       return true;
268:     }
269: 
270:     const SEBagValveMaskInstantaneous* inst = dynamic_cast<const SEBagValveMaskInstantaneous*>(&action);
271:     if (inst != nullptr)
272:     {
273:       if (HasBagValveMaskSqueeze())
274:       {
275:         Warning("Replacing active BagValveMaskSqueeze action with this BagValveMaskInstantaneous action");
276:       }
277:       if (HasBagValveMaskAutomated())
278:       {
279:         Warning("Replacing active BagValveMaskAutomated action with this BagValveMaskInstantaneous action");
280:       }
281:       RemoveBagValveMaskSqueeze();
282:       RemoveBagValveMaskAutomated();
283:       GetBagValveMaskInstantaneous().Copy(*inst);
284:       m_BagValveMaskInstantaneous->Activate();
285:       if (!m_BagValveMaskInstantaneous->IsActive())
286:         RemoveBagValveMaskInstantaneous();
287:       return true;
288:     }
289: 
290:     const SEBagValveMaskSqueeze* squeeze = dynamic_cast<const SEBagValveMaskSqueeze*>(&action);
291:     if (squeeze != nullptr)
292:     {
293:       if (HasBagValveMaskInstantaneous())
294:       {
295:         Warning("Replacing active BagValveMaskInstantaneous action with this BagValveMaskSqueeze action");
296:       }
297:       if (HasBagValveMaskSqueeze())
298:       {
299:         Warning("Current BagValveMaskSqueeze action has not completed, starting a new squeeze");
300:       }
```

## /home/private/project-301/engine-stable/src/cpp/engine/common/controller/Controller.cpp
```cpp
88:   void Data::SetAirwayMode(eAirwayMode mode)
89:   {
90:     if (mode == m_AirwayMode)
91:       return;// do nazing!
92:     if (mode != eAirwayMode::Free && m_AirwayMode != eAirwayMode::Free)
93:       throw CommonDataModelException("Can only change airway mode from the Free mode, Disable other equipment first.");
94:     if (!IsAirwayModeSupported(mode))
95:       throw CommonDataModelException("Unsupported airwaymode : " + eAirwayMode_Name(mode));
96:     if (m_Intubation == eSwitch::On)
97:     {
98:       if(m_AirwayMode == eAirwayMode::Inhaler)
99:         throw CommonDataModelException("Cannot apply inhaler if intubated.");
100:     }
101:     m_Compartments->UpdateAirwayGraph();
102:     m_AirwayMode = mode;
103:     std::stringstream ss;
104:     ss << "Airway Mode : " << eAirwayMode_Name(m_AirwayMode);
105:     Info(ss);
106:   }
107: 
108:   void Data::SetupTracker()
109:   {
110:     m_EngineTrack = new SEEngineTracker(*m_CurrentPatient, *m_Actions, *m_Substances, *m_Compartments, m_Logger);
```
```cpp
583:   void Controller::CheckIntubation()
584:   {
585:     if (m_Actions->GetPatientActions().HasIntubation())
586:     {
587:       if (m_Intubation == eSwitch::Off)
588:       {
589:         Info("Intubating Patient");
590:         m_Intubation = eSwitch::On;
591:       }
592:       return;
593:     }
594:     if (m_Intubation == eSwitch::On)
595:     {
596:       Info("Extubating Patient");
597:       m_Intubation = eSwitch::Off;
598:     }
599:   }
600: 
601:   bool Controller::AdvanceModelTime()
602:   {
603:     if (!IsReady())
604:       return false;
605: 
606:     try
607:     {
608:       CheckIntubation();
609:       PreProcess();
610:       Process();
611:       PostProcess();
612:     }catch (IrreversibleStateException&) { }
613: 
614:     if (m_EventManager->IsEventActive(eEvent::IrreversibleState))
615:     {
616:       m_State = EngineState::Fatal;
617:       return false;
618:     }
619: 
620:     m_EventManager->UpdateEvents(m_Config->GetTimeStep());
621:     m_CurrentTime.Increment(m_Config->GetTimeStep());
622:     m_SimulationTime.Increment(m_Config->GetTimeStep());
623: 
624:     if (m_AdvanceHandler)
625:       m_AdvanceHandler->OnAdvance(m_CurrentTime.GetValue(TimeUnit::s));
626: 
627:     // TODO Figure out a way to track what overrides were used and which were not
628:     m_ScalarOverrides.clear();
629: 
630:     return true;
631:   }
632: 
633:   bool Controller::AdvanceModelTime(double time, const TimeUnit& unit)
```
```cpp
828:     if (!GetActions().ProcessAction(action))
829:       return false;
830: 
831:     const SECardiovascularMechanicsModification* cvMod = dynamic_cast<const SECardiovascularMechanicsModification*>(&action);
832:     if (cvMod != nullptr && !cvMod->GetIncremental())
833:     {
834:       m_EventManager->SetEvent(eEvent::Stabilizing, true, m_SimulationTime);
835:       m_NervousModel->SetBaroreceptorFeedback(eSwitch::Off);
836:       m_NervousModel->SetChemoreceptorFeedback(eSwitch::Off);
837:       m_Config->GetStabilization()->TrackStabilization(eSwitch::On);
838:       if (!m_Config->GetStabilization()->Stabilize(*m_Stabilizer, SEEngineStabilization::AdvanceUntilStable))
839:         Error("Unable to restabilize to provided cardiovascular modifiers");
840:       m_Actions->GetPatientActions().GetCardiovascularMechanicsModification().SetIncremental(true);
841: 
842:       m_NervousModel->SetBaroreceptorFeedback(eSwitch::On);
843:       m_NervousModel->SetChemoreceptorFeedback(eSwitch::On);
844:       GetCurrentPatient().GetMeanArterialPressureBaseline().Set(GetCardiovascular().GetMeanArterialPressure());
845:       GetCurrentPatient().GetSystolicArterialPressureBaseline().Set(GetCardiovascular().GetSystolicArterialPressure());
846:       GetCurrentPatient().GetDiastolicArterialPressureBaseline().Set(GetCardiovascular().GetDiastolicArterialPressure());
847: 
848:       m_EventManager->SetEvent(eEvent::Stabilizing, false, m_SimulationTime);
849:     }
850: 
851:     const SERespiratoryMechanicsModification* rMod = dynamic_cast<const SERespiratoryMechanicsModification*>(&action);
852:     if (rMod != nullptr && !rMod->GetIncremental())
853:     {
854:       m_EventManager->SetEvent(eEvent::Stabilizing, true, m_SimulationTime);
855:       m_Config->GetStabilization()->TrackStabilization(eSwitch::On);
856:       if (!m_Config->GetStabilization()->Stabilize(*m_Stabilizer, SEEngineStabilization::AdvanceUntilStable))
857:         Error("Unable to restabilize to provided respiratory modifiers");
858:       m_Actions->GetPatientActions().GetRespiratoryMechanicsModification().SetIncremental(true);
859:       m_EventManager->SetEvent(eEvent::Stabilizing, false, m_SimulationTime);
860:     }
861: 
862:     return true;
863:   }
864: 
865:   void Controller::InitializeModels()
866:   {
867:     for (auto model : m_Models)
868:       model->Clear();
869:     Info("Initializing Models");
870:     for (auto model : m_Models)
871:       model->Initialize();
872:   }
873: 
874:   void Controller::AtSteadyState(pulse::EngineState state)
```

## /home/private/project-301/engine-stable/src/cpp/engine/common/system/physiology/DrugModel.cpp
```cpp
145:   void DrugModel::PreProcess()
146:   {
147:     AdministerSubstanceBolus();
148:     AdministerSubstanceInfusion();
149:     AdministerSubstanceCompoundInfusion();
150:   }
151: 
152:   //--------------------------------------------------------------------------------------------------
153:   /// \brief
154:   /// Substances process function
155:   ///
156:   /// \details
157:   /// For any drugs circulating in the system the renal and hepatic clearance factors and metabolic factors
158:   /// are assigned to the appropriate compartments.
159:   /// The drug effects categories and system level drug effects are calculated and the values are set on the common data
160:   /// model for use in other systems. Drug effects are only calculated if the PD is enabled.
161:   //--------------------------------------------------------------------------------------------------
162:   void DrugModel::Process(bool /*solve_and_transport*/)
163:   {
164:     CalculatePartitionCoefficients();
165: 
166:     CalculateSubstanceClearance();
167: 
168:     CalculatePlasmaSubstanceConcentration();
169: 
170:     if (m_data.GetConfiguration().IsPDEnabled())
171:       CalculateDrugEffects();
172:     ComputeExposedModelParameters();
173:   }
```
```cpp
193:   void DrugModel::AdministerSubstanceBolus()
194:   {
195:     //Need to loop over Bolus Dose Objects
196:     const std::vector<SESubstanceBolus*>& boluses = m_data.GetActions().GetPatientActions().GetSubstanceBoluses();
197:     if (boluses.empty())
198:       return;
199: 
200:     std::vector<const SESubstance*> completedBolus;
201:     const SESubstance* sub;
202:     SELiquidSubstanceQuantity* subQ;
203:     double dose_mL;
204:     double concentration_ugPermL;
205:     double massIncrement_ug = 0;
206:     double administrationTime_s;
207: 
208:     for (auto bolus : boluses)
209:     {
210:       if (!bolus->IsActive())
211:         continue;
212: 
213:       dose_mL = bolus->GetDose(VolumeUnit::mL);
214:       if (bolus->GetTotalInfusedDose().GetValue(VolumeUnit::mL) >= dose_mL)
215:       {
216:         // Finished, remove it
217:         completedBolus.push_back(&bolus->GetSubstance());
218:         continue;
219:       }
220: 
221:       sub = &bolus->GetSubstance();
222:       switch (bolus->GetAdminRoute())
223:       {
224:       case eSubstanceAdministration_Route::Intraarterial:
225:         subQ = m_aortaVascular->GetSubstanceQuantity(*sub);
226:         break;
227:       case eSubstanceAdministration_Route::Intravenous:
228:         subQ = m_venaCavaVascular->GetSubstanceQuantity(*sub);
229:         break;
230:       case eSubstanceAdministration_Route::Intramuscular:
231:         subQ = m_muscleIntracellular->GetSubstanceQuantity(*sub);
232:         break;
233:       default:
234:         Error("Unavailable Bolus Administration Route for substance " + sub->GetName());
235:         completedBolus.push_back(sub);// Remove it
236:         continue;
237:       }
238: 
239:       if (!bolus->HasAdminDuration())
240:       {
241:         bolus->GetAdminDuration().SetValue(2, TimeUnit::s);
242:         Info("Defaulting bolus administration duration of " + sub->GetName() + " to 2s");
243:       }
244:       administrationTime_s = bolus->GetAdminDuration(TimeUnit::s);
245:       concentration_ugPermL = bolus->GetConcentration(MassPerVolumeUnit::ug_Per_mL);
246:       massIncrement_ug = dose_mL * concentration_ugPermL * m_data.GetTimeStep_s() / administrationTime_s;
247:       subQ->GetMass().Increment(massIncrement_ug, MassUnit::ug);
248:       subQ->Balance(BalanceLiquidBy::Mass);
249:       bolus->GetTotalInfusedDose().Increment(massIncrement_ug / concentration_ugPermL, VolumeUnit::mL);
250:       /// \todo Add fluid amount to fluid system
251:     }
252:     // Remove any bolus that are complete
253:     for (const SESubstance* s : completedBolus)
254:       m_data.GetActions().GetPatientActions().RemoveSubstanceBolus(*s);
255:   }
256: 
257:   //--------------------------------------------------------------------------------------------------
258:   /// \brief
259:   /// Increments the mass of a substance to represent drug infusion
260:   ///
261:   /// \details
262:   /// The mass of a substance is increased based on the administration of a substance. 
263:   /// For an infusion, the user specifies a concentration and a rate. The calculated mass
264:   /// is then added to the vena cava every time step until the infusion is stopped.
265:   //--------------------------------------------------------------------------------------------------
266:   void DrugModel::AdministerSubstanceInfusion()
267:   {
268:     const std::vector<SESubstanceInfusion*>& infusions = m_data.GetActions().GetPatientActions().GetSubstanceInfusions();
269:     if (infusions.empty())
270:       return;
271: 
272:     SELiquidSubstanceQuantity* subQ;
273:     double concentration_ug_Per_mL;
274:     double rate_mL_Per_s;
275:     double massIncrement_ug = 0;
276:     std::vector<const SESubstance*> finished;
277: 
278:     for (auto infusion : infusions)
279:     {
280:       if (!infusion->IsActive())
281:         continue;
282: 
283:       if (!infusion->HasVolume())
284:         infusion->GetVolume().SetValue(1000, VolumeUnit::mL);
285: 
286:       concentration_ug_Per_mL = infusion->GetConcentration().GetValue(MassPerVolumeUnit::ug_Per_mL);
287:       rate_mL_Per_s = infusion->GetRate().GetValue(VolumePerTimeUnit::mL_Per_s);
288:       infusion->GetVolume().Increment(-rate_mL_Per_s * m_data.GetTimeStep_s(), VolumeUnit::mL);
289:       if (infusion->GetVolume().IsZero() || infusion->GetVolume().IsNegative())
290:       { /// \todo correct the mass based on what we have left in the bag
291:         finished.push_back(&infusion->GetSubstance());
292:         continue;
293:       }
294: 
295:       massIncrement_ug = rate_mL_Per_s * concentration_ug_Per_mL * m_data.GetTimeStep_s();
296:       subQ = m_venaCavaVascular->GetSubstanceQuantity(infusion->GetSubstance());
297:       subQ->GetMass().Increment(massIncrement_ug, MassUnit::ug);
298:       //todo: Enforce limits and remove the fatal error
299:       if (massIncrement_ug < 0)
300:       {
301:         std::stringstream AdministeredTitrationDoseError;
302:         AdministeredTitrationDoseError << "Cannot specify a dose of less than 0. Current dose is: " << massIncrement_ug << " ug";
303:         Fatal(AdministeredTitrationDoseError);
304:         return;
305:       }
306: 
307:       /// \todo Need to add fluid amount to fluid system
308:     }
309:     for (const SESubstance* sub : finished)
310:     {
311:       Info("Completed infusion of " + sub->GetName());
312:       m_data.GetActions().GetPatientActions().RemoveSubstanceInfusion(*sub);
313:     }
314:   }
315: 
316:   //--------------------------------------------------------------------------------------------------
317:   /// \brief
318:   /// Increases the substance masses for compounds
319:   ///
320:   /// \details
321:   /// The masses of all substances associated with the compound substance are increased.
322:   /// The mass of each substance is incremented in the vena cava based on the rate specified by the user 
323:   /// and a concentration specified in the compound substance file.
324:   //--------------------------------------------------------------------------------------------------
325:   void DrugModel::AdministerSubstanceCompoundInfusion()
326:   {
327:     const std::vector<SESubstanceCompoundInfusion*>& infusions = m_data.GetActions().GetPatientActions().GetSubstanceCompoundInfusions();
328:     if (infusions.empty())
329:       return;
330: 
331:     const SESubstanceCompound* compound;
332:     SELiquidSubstanceQuantity* subQ;
333:     double rate_mL_Per_s = 0;
334:     double totalRate_mL_Per_s = 0;
335:     double massIncrement_ug = 0;
336: 
337:     std::vector<const SESubstanceCompound*> emptyBags;
338: 
339:     for (auto infusion : infusions)
340:     {
341:       compound = &infusion->GetSubstanceCompound();
342: 
343:       if (!infusion->IsActive())
344:         continue;
345: 
346:       rate_mL_Per_s = infusion->GetRate().GetValue(VolumePerTimeUnit::mL_Per_s);
347:       totalRate_mL_Per_s += rate_mL_Per_s;
348:       //todo: Enforce limits and remove the fatal error
349:       if (rate_mL_Per_s > 285) // from http://emedsa.org.au/EDHandbook/resuscitation/IVCannula.htm... 1000mL/3.5 min ~= 285 mL/min
350:       {
351:         m_ss << "Cannot specify an Infusion rate greater than 285 mL/min. Current administration rate is: " << infusion->GetRate();
352:         Fatal(m_ss);
353:         return;
354:       }
355: 
356:       infusion->GetBagVolume().Increment(-rate_mL_Per_s * m_data.GetTimeStep_s(), VolumeUnit::mL);
357:       if (infusion->GetBagVolume().IsZero() || infusion->GetBagVolume().IsNegative())
358:       { /// \todo correct the mass based on what we have left in the bag
359:         emptyBags.push_back(compound);
360:         continue;
361:       }
362: 
363:       for (const SESubstanceConcentration* component : compound->GetComponents())
364:       {
365:         subQ = m_venaCavaVascular->GetSubstanceQuantity(component->GetSubstance());
366:         massIncrement_ug = rate_mL_Per_s * component->GetConcentration(MassPerVolumeUnit::ug_Per_mL) * m_data.GetTimeStep_s();
367:         subQ->GetMass().Increment(massIncrement_ug, MassUnit::ug);
368:         subQ->Balance(BalanceLiquidBy::Mass);
369:       }
370:     }
371: 
372:     for (const SESubstanceCompound* c : emptyBags)
373:     {
374:       Info("Completed infusion of " + c->GetName());
375:       m_data.GetActions().GetPatientActions().RemoveSubstanceCompoundInfusion(*c);
376:     }
377: 
378:     m_IVToVenaCava->GetNextFlowSource().SetValue(totalRate_mL_Per_s, VolumePerTimeUnit::mL_Per_s);
379:   }
380: 
381:   //--------------------------------------------------------------------------------------------------
382:   /// \brief
383:   /// Calculate partition coefficients for the PK Model
384:   ///
385:   /// \param  vSubstances
386:   /// Coefficients are calculated for the substances in the vector with IonicState. 
387:   /// 
388:   /// \details
389:   /// The partition coefficients are calculated for each substance in the input vector (active substances). 
390:   /// To ensure the diffusion is modeled with PK for the substance, a check is performed for Ionic State. If 
```
```cpp
515:   void DrugModel::CalculateDrugEffects()
516:   {
517:     double deltaHeartRate_Per_min = 0;
518:     double deltaDiastolicBP_mmHg = 0;
519:     double deltaSystolicBP_mmHg = 0;
520:     double deltaRespirationRate_Per_min = 0;
521:     double deltaTidalVolume_mL = 0;
522:     double neuromuscularBlockLevel = 0;
523:     double sedationLevel = 0;
524:     double bronchodilationLevel = 0;
525:     double plasmaConcentration_ug_Per_mL = 0;
526:     double concentrationEffects_unitless = 0;
527:     double deltaTubularPermeability = 0.0;
528:     double pupilSizeResponseLevel = 0;
529:     double pupilReactivityResponseLevel = 0;
530:     double shapeParameter = 1.;
531:     SEPatient& patient = m_data.GetCurrentPatient();
532:     double HRBaseline_per_min = patient.GetHeartRateBaseline(FrequencyUnit::Per_min);
533: 
534:     //Loop over substances
535:     for (SESubstance* sub : m_data.GetCompartments().GetLiquidCompartmentSubstances())
536:     {
537:       if (!sub->HasPD())
538:         continue;
539: 
540:       const SESubstancePharmacodynamics& pd = sub->GetPD();
541:       plasmaConcentration_ug_Per_mL = sub->GetPlasmaConcentration(MassPerVolumeUnit::ug_Per_mL);
542:       shapeParameter = pd.GetEMaxShapeParameter();
543:       if (shapeParameter == 1) // Avoiding using pow if we don't have to. I don't know if this is good practice or not, but seems legit.
544:         concentrationEffects_unitless = plasmaConcentration_ug_Per_mL / (pd.GetEC50(MassPerVolumeUnit::ug_Per_mL) + plasmaConcentration_ug_Per_mL);
545:       else
546:         concentrationEffects_unitless = pow(plasmaConcentration_ug_Per_mL, shapeParameter) / (pow(pd.GetEC50(MassPerVolumeUnit::ug_Per_mL), shapeParameter) + pow(plasmaConcentration_ug_Per_mL, shapeParameter));
547:       /// \todo The drug effect is being applied to the baseline, so if the baseline changes the delta heart rate changes.
548:       // This would be a problem for something like a continuous infusion of a drug or an environmental drug
549:       // where we need to establish a new homeostatic point. Once the patient stabilizes with the drug effect included, a new baseline is
550:       // set, and suddenly the drug effect is being computed using the new baseline. We may need to add another layer of 
551:       // stabilization and restrict drugs to post-feedback stabilization. Alternatively, we could base the drug effect on a baseline
552:       // concentration which is normally zero but which gets set to a new baseline concentration at the end of feedback (see chemoreceptor
553:       // and the blood gas setpoint reset for example).
554:       deltaHeartRate_Per_min += HRBaseline_per_min * pd.GetHeartRateModifier() * concentrationEffects_unitless;
555: 
556:       deltaDiastolicBP_mmHg += patient.GetDiastolicArterialPressureBaseline(PressureUnit::mmHg) * pd.GetDiastolicPressureModifier() * concentrationEffects_unitless;
557: 
558:       deltaSystolicBP_mmHg += patient.GetSystolicArterialPressureBaseline(PressureUnit::mmHg) * pd.GetSystolicPressureModifier() * concentrationEffects_unitless;
559: 
560:       sedationLevel += pd.GetSedation() * concentrationEffects_unitless;
561: 
562:       deltaTubularPermeability += (pd.GetTubularPermeabilityModifier()) * concentrationEffects_unitless;
563: 
564:       if (sedationLevel > 0.999)//0.15)
565:       {
566:         deltaRespirationRate_Per_min += patient.GetRespirationRateBaseline(FrequencyUnit::Per_min) * pd.GetRespirationRateModifier();
567:         deltaTidalVolume_mL += patient.GetTidalVolumeBaseline(VolumeUnit::mL) * pd.GetTidalVolumeModifier();
568:       }
569:       else
570:       {
571:         deltaRespirationRate_Per_min += patient.GetRespirationRateBaseline(FrequencyUnit::Per_min) * pd.GetRespirationRateModifier() * concentrationEffects_unitless;
572:         deltaTidalVolume_mL += patient.GetTidalVolumeBaseline(VolumeUnit::mL) * pd.GetTidalVolumeModifier() * concentrationEffects_unitless;
573:       }
574: 
575:       neuromuscularBlockLevel += pd.GetNeuromuscularBlock() * concentrationEffects_unitless;
576:       bronchodilationLevel += pd.GetBronchodilation() * concentrationEffects_unitless;
577: 
578:       const SEPupillaryResponse* pr = pd.GetPupillaryResponse();
579:       pupilSizeResponseLevel += pr->GetSizeModifier() * concentrationEffects_unitless;
580:       pupilReactivityResponseLevel += pr->GetReactivityModifier() * concentrationEffects_unitless;
581:     }
582: 
583:     //Translate Diastolic and Systolic Pressure to pulse pressure and mean pressure
584:     double deltaMeanPressure_mmHg = (2 * deltaDiastolicBP_mmHg + deltaSystolicBP_mmHg) / 3;
585: 
586:     double deltaPulsePressure_mmHg = deltaSystolicBP_mmHg - deltaDiastolicBP_mmHg;
587: 
588:     //Bound things that are fractions
589:     sedationLevel = LIMIT(sedationLevel, 0.0, 1.0);
590:     bronchodilationLevel = LIMIT(bronchodilationLevel, -1.0, 1.0);
591:     neuromuscularBlockLevel = LIMIT(neuromuscularBlockLevel, 0.0, 1.0);
592:     deltaTubularPermeability = LIMIT(deltaTubularPermeability, -1.0, 1.0);
593: 
594:     //Set values on the CDM System Values
595:     GetHeartRateChange().SetValue(deltaHeartRate_Per_min, FrequencyUnit::Per_min);
596:     GetMeanBloodPressureChange().SetValue(deltaMeanPressure_mmHg, PressureUnit::mmHg);
597:     GetPulsePressureChange().SetValue(deltaPulsePressure_mmHg, PressureUnit::mmHg);
598:     GetRespirationRateChange().SetValue(deltaRespirationRate_Per_min, FrequencyUnit::Per_min);
599:     GetTidalVolumeChange().SetValue(deltaTidalVolume_mL, VolumeUnit::mL);
600:     GetNeuromuscularBlockLevel().SetValue(neuromuscularBlockLevel);
601:     GetSedationLevel().SetValue(sedationLevel);
602:     GetBronchodilationLevel().SetValue(bronchodilationLevel);
603:     GetTubularPermeabilityChange().SetValue(deltaTubularPermeability);
604: 
605: 
606:     // Bound the pupil modifiers
607:     BLIM(pupilSizeResponseLevel, -1, 1);
608:     BLIM(pupilReactivityResponseLevel, -1, 1);
609:     GetPupillaryResponse().GetSizeModifier().SetValue(pupilSizeResponseLevel);
610:     GetPupillaryResponse().GetReactivityModifier().SetValue(pupilReactivityResponseLevel);
611:   }
612: 
613:   //--------------------------------------------------------------------------------------------------
614:   /// \brief
615:   /// Calculates the concentration of a substance in the plasma
616:   ///
617:   /// \details
618:   /// If the substance has PK properties, the concentration of the substance in the plasma is calculated. 
619:   /// PlasmaConcentration = TotalMassInTheBlood / PlasmaVolume.
620:   /// The plasma concentration is then set on the substance.
621:   /// The concentration computation is obviously erroneous. This is a known issue. See @ref pharmacokinetics
622:   //--------------------------------------------------------------------------------------------------
623:   void DrugModel::CalculatePlasmaSubstanceConcentration()
624:   {
625:     double PlasmaMass_ug = 0;
626:     double PlasmaVolume_mL = m_data.GetBloodChemistry().GetPlasmaVolume(VolumeUnit::mL);
627: 
628:     for (SESubstance* sub : m_data.GetCompartments().GetLiquidCompartmentSubstances())
629:     {
630:       PlasmaMass_ug = m_data.GetSubstances().GetSubstanceMass(*sub, m_data.GetCompartments().GetVascularLeafCompartments(), MassUnit::ug);
631:       sub->GetPlasmaConcentration().SetValue(PlasmaMass_ug / PlasmaVolume_mL, MassPerVolumeUnit::ug_Per_mL);
632:     }
633:   }
634: 
635:   //--------------------------------------------------------------------------------------------------
636:   /// \brief
637:   /// Calculates the substance mass cleared
638:   ///
639:   /// \details
640:   /// If the substance has PK properties, the substance clearance is calculated. The renal, liver, and systemic 
```

## /home/private/project-301/engine-stable/src/cpp/engine/common/system/physiology/RespiratoryModel.cpp
```cpp
1090:   /// This will provide supplemental oxygen by connecting and updating the circuit and graph for nasal
1091:   /// cannula, simple mask, or nonrebreather mask
1092:   //--------------------------------------------------------------------------------------------------
1093:   void RespiratoryModel::SupplementalOxygen()
1094:   {
1095:     ///\todo - Maybe this and mechanical ventilation should be broken out to their own class, like anesthesia machine?
1096: 
1097:     if (!m_PatientActions->HasSupplementalOxygen())
1098:       return;
1099:     SESupplementalOxygen& so = m_PatientActions->GetSupplementalOxygen();
1100: 
1101:     // Get flow
1102:     double flow_L_Per_min = 0;
1103:     if(so.HasFlow())
1104:       flow_L_Per_min = so.GetFlow(VolumePerTimeUnit::L_Per_min);
1105:     //Get tank pressure node and flow control resistor path
1106:     SEFluidCircuitPath* Tank = nullptr;
1107:     SEFluidCircuitPath* OxygenInlet = nullptr;
1108:     SEFluidCircuit* RespirationCircuit = nullptr;
1109:     switch (so.GetDevice())
1110:     {
1111:       case eSupplementalOxygen_Device::None:
1112:       {
1113:         m_data.SetAirwayMode(eAirwayMode::Free);
1114:         m_PatientActions->RemoveSupplementalOxygen();
1115:         return;
1116:       }
1117:       case eSupplementalOxygen_Device::NasalCannula:
1118:       {
1119:         // This implementation can replace other Supplemental O2 modes
1120:         if (m_data.GetAirwayMode() == eAirwayMode::SimpleMask ||
1121:             m_data.GetAirwayMode() == eAirwayMode::NonRebreatherMask)
1122:           m_data.SetAirwayMode(eAirwayMode::Free);
1123: 
1124:         m_data.SetAirwayMode(eAirwayMode::NasalCannula);
1125:         if (!so.HasFlow())
1126:         {
1127:           flow_L_Per_min = 3.5;
1128:           so.GetFlow().SetValue(flow_L_Per_min, VolumePerTimeUnit::L_Per_min);
1129:           Info("Supplemental oxygen flow not set. Using default value of " + cdm::to_string(flow_L_Per_min) + " L/min.");
1130:         }
1131:         RespirationCircuit = &m_data.GetCircuits().GetActiveRespiratoryCircuit();
1132:         OxygenInlet = RespirationCircuit->GetPath(pulse::NasalCannulaPath::NasalCannulaOxygenInlet);
1133:         Tank = RespirationCircuit->GetPath(pulse::NasalCannulaPath::NasalCannulaPressure);
1134:         break;
1135:       }
1136:       case eSupplementalOxygen_Device::NonRebreatherMask:
1137:       {
1138:         // This implementation can replace other Supplemental O2 modes
1139:         if (m_data.GetAirwayMode() == eAirwayMode::SimpleMask ||
1140:             m_data.GetAirwayMode() == eAirwayMode::NasalCannula)
1141:           m_data.SetAirwayMode(eAirwayMode::Free);
1142:         m_data.SetAirwayMode(eAirwayMode::NonRebreatherMask);
1143: 
1144:         if (!so.HasFlow())
1145:         {
1146:           flow_L_Per_min = 10.0;
1147:           so.GetFlow().SetValue(flow_L_Per_min, VolumePerTimeUnit::L_Per_min);
1148:           Info("Supplemental oxygen flow not set. Using default value of " + cdm::to_string(flow_L_Per_min) + " L/min.");
1149:         }
1150:         RespirationCircuit = &m_data.GetCircuits().GetActiveRespiratoryCircuit();
1151:         OxygenInlet = RespirationCircuit->GetPath(pulse::NonRebreatherMaskPath::NonRebreatherMaskOxygenInlet);
1152:         Tank = RespirationCircuit->GetPath(pulse::NonRebreatherMaskPath::NonRebreatherMaskPressure);
1153:         break;
1154:       }
1155:       case eSupplementalOxygen_Device::SimpleMask:
1156:       {
1157:         // This implementation can replace other Supplemental O2 modes
1158:         if (m_data.GetAirwayMode() == eAirwayMode::NasalCannula ||
1159:             m_data.GetAirwayMode() == eAirwayMode::NonRebreatherMask)
1160:           m_data.SetAirwayMode(eAirwayMode::Free);
1161:         m_data.SetAirwayMode(eAirwayMode::SimpleMask);
1162: 
1163:         if (!so.HasFlow())
1164:         {
1165:           flow_L_Per_min = 7.5;
1166:           so.GetFlow().SetValue(flow_L_Per_min, VolumePerTimeUnit::L_Per_min);
1167:           Info("Supplemental oxygen flow not set. Using default value of " + cdm::to_string(flow_L_Per_min) + " L/min.");
1168:         }
1169:         RespirationCircuit = &m_data.GetCircuits().GetActiveRespiratoryCircuit();
1170:         OxygenInlet = RespirationCircuit->GetPath(pulse::SimpleMaskPath::SimpleMaskOxygenInlet);
1171:         Tank = RespirationCircuit->GetPath(pulse::SimpleMaskPath::SimpleMaskPressure);
1172:         break;
1173:       }
1174:       default:
1175:       {
1176:         Error("Ignoring unsupported supplemental oxygen type : " + eSupplementalOxygen_Device_Name(so.GetDevice()));
1177:         return;
1178:       }
1179:     }
1180: 
1181:     //Use a default tank volume if it wasn't explicity set
1182:     if (!so.HasVolume())
1183:     {
1184:       so.GetVolume().SetValue(425.0, VolumeUnit::L);
1185:       Info("Supplemental oxygen initial tank volume not set. Using default value of 425 L.");
1186:     }
1187: 
1188:     //Decrement volume from the tank
1189:     //Inf volume is assumed to be a wall connection that will never run out
1190:     if (so.GetVolume(VolumeUnit::L) != std::numeric_limits<double>::infinity())
```
```cpp
1730:       double NeedleResistance_cmH2O_s_Per_L = 100.0;
1731: 
1732:       if (m_PatientActions->HasLeftOpenTensionPneumothorax())
1733:       {
1734:         // Scale the flow resistance through the chest opening based on severity
1735:         double severity = m_PatientActions->GetLeftOpenTensionPneumothorax().GetSeverity().GetValue();
1736:         double resistance_cmH2O_s_Per_L = PneumoMaxResistance_cmH2O_s_Per_L;
1737:         if (severity > 0.0 && !m_PatientActions->HasLeftChestOcclusiveDressing())
1738:         {
1739:           resistance_cmH2O_s_Per_L = PneumoMinResistance_cmH2O_s_Per_L / pow(severity, 2.0);
1740:         }
1741:         resistance_cmH2O_s_Per_L = MIN(resistance_cmH2O_s_Per_L, PneumoMaxResistance_cmH2O_s_Per_L);
1742:         m_EnvironmentToLeftChestLeak->GetNextResistance().SetValue(resistance_cmH2O_s_Per_L, PressureTimePerVolumeUnit::cmH2O_s_Per_L);
1743: 
1744:         if (m_PatientActions->HasLeftNeedleDecompression())
1745:         {
1746:           m_LeftNeedleToLeftPleural->GetNextResistance().SetValue(NeedleResistance_cmH2O_s_Per_L, PressureTimePerVolumeUnit::cmH2O_s_Per_L);
1747:         }
1748:       }
1749: 
1750:       if (m_PatientActions->HasRightOpenTensionPneumothorax())
1751:       {
1752:         // Scale the flow resistance through the chest opening based on severity
1753:         double severity = m_PatientActions->GetRightOpenTensionPneumothorax().GetSeverity().GetValue();
1754:         double resistance_cmH2O_s_Per_L = PneumoMaxResistance_cmH2O_s_Per_L;
1755:         if (severity > 0.0 && !m_PatientActions->HasRightChestOcclusiveDressing())
1756:         {
1757:           resistance_cmH2O_s_Per_L = PneumoMinResistance_cmH2O_s_Per_L / pow(severity, 2.0);
1758:         }
1759:         resistance_cmH2O_s_Per_L = MIN(resistance_cmH2O_s_Per_L, PneumoMaxResistance_cmH2O_s_Per_L);
1760:         m_EnvironmentToRightChestLeak->GetNextResistance().SetValue(resistance_cmH2O_s_Per_L, PressureTimePerVolumeUnit::cmH2O_s_Per_L);
1761: 
1762:         if (m_PatientActions->HasRightNeedleDecompression())
1763:         {
1764:           m_RightNeedleToRightPleural->GetNextResistance().SetValue(NeedleResistance_cmH2O_s_Per_L, PressureTimePerVolumeUnit::cmH2O_s_Per_L);
1765:         }
1766:         m_EnvironmentToRightChestLeak->GetNextResistance().SetValue(resistance_cmH2O_s_Per_L, PressureTimePerVolumeUnit::cmH2O_s_Per_L);
1767:       }
1768: 
1769:       if (m_PatientActions->HasLeftClosedTensionPneumothorax())
1770:       {
1771:         // Scale the flow resistance through the chest opening based on severity
1772:         double severity = m_PatientActions->GetLeftClosedTensionPneumothorax().GetSeverity().GetValue();
1773:         double resistance_cmH2O_s_Per_L = PneumoMaxResistance_cmH2O_s_Per_L;
1774:         if (severity > 0.0)
1775:         {
1776:           resistance_cmH2O_s_Per_L = PneumoMinResistance_cmH2O_s_Per_L / pow(severity, 2.0);
1777:         }
1778:         resistance_cmH2O_s_Per_L = MIN(resistance_cmH2O_s_Per_L, PneumoMaxResistance_cmH2O_s_Per_L);
1779:         m_LeftAlveoliLeakToLeftPleural->GetNextResistance().SetValue(resistance_cmH2O_s_Per_L, PressureTimePerVolumeUnit::cmH2O_s_Per_L);
1780: 
1781:         if (m_PatientActions->HasLeftNeedleDecompression())
1782:         {
1783:           m_LeftNeedleToLeftPleural->GetNextResistance().SetValue(NeedleResistance_cmH2O_s_Per_L, PressureTimePerVolumeUnit::cmH2O_s_Per_L);
1784:         }
1785:       }
1786: 
1787:       if (m_PatientActions->HasRightClosedTensionPneumothorax())
1788:       {
1789:         // Scale the flow resistance through the chest opening based on severity
1790:         double severity = m_PatientActions->GetRightClosedTensionPneumothorax().GetSeverity().GetValue();
1791:         double resistance_cmH2O_s_Per_L = PneumoMaxResistance_cmH2O_s_Per_L;
1792:         if (severity > 0.0)
1793:         {
1794:           resistance_cmH2O_s_Per_L = PneumoMinResistance_cmH2O_s_Per_L / pow(severity, 2.0);
1795:         }
1796:         resistance_cmH2O_s_Per_L = MIN(resistance_cmH2O_s_Per_L, PneumoMaxResistance_cmH2O_s_Per_L);
1797:         m_RightAlveoliLeakToRightPleural->GetNextResistance().SetValue(resistance_cmH2O_s_Per_L, PressureTimePerVolumeUnit::cmH2O_s_Per_L);
1798: 
1799:         if (m_PatientActions->HasRightNeedleDecompression())
1800:         {
1801:           m_RightNeedleToRightPleural->GetNextResistance().SetValue(NeedleResistance_cmH2O_s_Per_L, PressureTimePerVolumeUnit::cmH2O_s_Per_L);
1802:         }
1803:       }
1804: 
1805:       //Check for interventions without insult
1806:       if (!m_PatientActions->HasLeftClosedTensionPneumothorax() && !m_PatientActions->HasLeftOpenTensionPneumothorax())
1807:       {
1808:         if (m_PatientActions->HasLeftChestOcclusiveDressing() || m_PatientActions->HasLeftNeedleDecompression())
1809:         {
1810:           Error("Cannot perform an intervention if Tension Pneumothorax is not present on that side.");
1811:           m_PatientActions->RemoveLeftChestOcclusiveDressing();
1812:           m_PatientActions->RemoveLeftNeedleDecompression();
1813:           return;
1814:         }
1815:       }
1816:       if (!m_PatientActions->HasRightClosedTensionPneumothorax() && !m_PatientActions->HasRightOpenTensionPneumothorax())
1817:       {
1818:         if (m_PatientActions->HasRightChestOcclusiveDressing() || m_PatientActions->HasRightNeedleDecompression())
1819:         {
1820:           Error("Cannot perform an intervention if Tension Pneumothorax is not present on that side.");
1821:           m_PatientActions->RemoveRightChestOcclusiveDressing();
1822:           m_PatientActions->RemoveRightNeedleDecompression();
1823:           return;
1824:         }
1825:       }
1826:     }
1827:     else
1828:     {
1829:       // Check for cases where the needle decompression or occlusive dressing actions are called without having
1830:       // initiated a pneumothorax action
1831:       if (m_PatientActions->HasNeedleDecompression())
1832:       {
1833:         Error("Cannot perform a Needle Decompression intervention if Tension Pneumothorax is not present");
1834:         m_PatientActions->RemoveLeftNeedleDecompression();
1835:         m_PatientActions->RemoveRightNeedleDecompression();
1836:         return;
1837:       }
1838:       if (m_PatientActions->HasChestOcclusiveDressing())
1839:       {
1840:         Error("Cannot perform a Chest Occlusive Dressing intervention if Tension Pneumothorax is not present");
1841:         m_PatientActions->RemoveLeftChestOcclusiveDressing();
1842:         m_PatientActions->RemoveRightChestOcclusiveDressing();
1843:         return;
1844:       }
1845:     }
```
```cpp
1870:     {
1871:       if(m_LeftCardiovascularLeak == nullptr)
1872:        m_LeftCardiovascularLeak = m_data.GetCircuits().GetActiveCardiovascularCircuit().GetPath(pulse::CardiovascularPath::LeftPulmonaryVeinsLeak1ToGround);
1873: 
1874:       if (m_LeftCardiovascularLeak != nullptr)
1875:       {
1876:         //Blood coming in
1877:         if (m_LeftCardiovascularLeak->HasNextFlow())
1878:         {
1879:           leftBloodFlow_L_Per_s += m_LeftCardiovascularLeak->GetNextFlow(VolumePerTimeUnit::L_Per_s);
1880:         }
1881:       }
1882:     }
1883: 
1884:     bool hasLeftTubeThoracostomy = m_PatientActions->HasLeftTubeThoracostomy();
1885:     if (hasLeftTubeThoracostomy)
1886:     {
1887:       //Default 200 mL/day \cite hessami2009volume
1888:       double thoracostomyFlowRate_L_Per_s = 2.31e-6;
1889:       if (m_PatientActions->GetLeftTubeThoracostomy().HasFlowRate())
1890:       {
1891:         thoracostomyFlowRate_L_Per_s = m_PatientActions->GetLeftTubeThoracostomy().GetFlowRate(VolumePerTimeUnit::L_Per_s);
1892:         if (thoracostomyFlowRate_L_Per_s > 0.001)
1893:         {
1894:           Error("Tube thoracostomy flow rate is above maximum allowable value. Overriding to 1 mL/s.");
1895:           thoracostomyFlowRate_L_Per_s = 0.001;
1896:           m_data.GetActions().GetPatientActions().GetLeftTubeThoracostomy().GetFlowRate().SetValue(thoracostomyFlowRate_L_Per_s, VolumePerTimeUnit::L_Per_s);
1897:         }
1898:       }
1899:       //Blood going out
1900:       leftBloodFlow_L_Per_s -= thoracostomyFlowRate_L_Per_s;
1901:     }
1902: 
1903:     if (leftBloodFlow_L_Per_s != 0.0)
1904:     {
1905:       if (m_LeftRespirtoryLeak == nullptr)
1906:       {
1907:         //Create the left chest leak in the circuit (no updates to graph needed)
1908:         m_LeftRespirtoryLeak = &m_RespiratoryCircuit->CreatePath(*m_AmbientNode, *m_LeftPleuralNode, pulse::RespiratoryPath::EnvironmentToLeftPleural);
1909:         m_LeftRespirtoryLeak->GetFlowSourceBaseline().SetValue(0.0, VolumePerTimeUnit::L_Per_s);
1910:         stateChange = true;
1911:       }
1912: 
1913:       if (m_PatientActions->GetLeftHemothorax().HasTotalBloodVolume())
1914:       {
1915:         m_PatientActions->GetLeftHemothorax().GetTotalBloodVolume().Increment(leftBloodFlow_L_Per_s * m_data.GetTimeStep_s(), VolumeUnit::L);
1916:       }
1917:       else
1918:       {
1919:         m_PatientActions->GetLeftHemothorax().GetTotalBloodVolume().SetValue(leftBloodFlow_L_Per_s * m_data.GetTimeStep_s(), VolumeUnit::L);
1920:       }
1921: 
1922:       if (m_PatientActions->GetLeftHemothorax().GetTotalBloodVolume(VolumeUnit::L) > maxVolume_L)
1923:       {
1924:         Error("Maximum left hemothorax volume exceeded. Removing left hemothorax");
1925:         m_PatientActions->GetLeftHemothorax().GetFlowRate().SetValue(0.0, VolumePerTimeUnit::L_Per_s);
1926:         if (m_PatientActions->GetLeftHemothorax().HasSeverity())
1927:         {
1928:           m_PatientActions->GetLeftHemothorax().GetSeverity().SetValue(0.0);
1929:         }
1930:       }
1931:       else
1932:       {
1933:         m_RespiratoryCircuit->GetPath(pulse::RespiratoryPath::EnvironmentToLeftPleural)->GetNextFlowSource().SetValue(factor * leftBloodFlow_L_Per_s, VolumePerTimeUnit::L_Per_s);
1934:       }
1935: 
1936:       if (hasLeftTubeThoracostomy &&
1937:           m_PatientActions->GetLeftHemothorax().GetTotalBloodVolume().IsNegative() &&
1938:           m_PatientActions->GetLeftTubeThoracostomy().GetFlowRate().IsPositive())
1939:       {
1940:         Info("Left Tube Thoracostomy has removed all blood. Setting flow rate to 0.");
```

## /home/private/project-301/engine-stable/src/cpp/cdm/substance/SESubstanceManager.cpp
```cpp
271: bool SESubstanceManager::LoadSubstanceDirectory(const std::string& data_dir)
272: {
273:   bool succeed = true;
274:   Clear();
275:   
276:   Info("Reading substance files from " + data_dir);
277:   if (!FileExists(data_dir + "/substances/"))
278:   {
279:     Error("Unable to find substance directory : " + data_dir);
280:     return false;
281:   }
282: 
283:   std::vector<std::string> substances;
284:   ListFiles(data_dir+"/substances/", substances, false, ".json");
285:   if (substances.empty())
286:     Error("No substances found...");
287: 
288:   std::vector<std::string> compounds;
289:   ListFiles(data_dir+"/substances/compounds/", compounds, false, ".json");
290:   if (substances.empty())
291:     Error("No substance compounds found...");
292: 
293:   std::string name, ext;
294:   for (auto filename : substances)
295:   {
296:     try
297:     {
298:       // I am assuming the filename is also the substance name
299:       // If we don't want to make that assumption, we need to have
300:       // a map of filename to substance ptr and use it rather than GetSubstance by name.
301:       SplitFilenameExt(filename, name, ext);
302:       if (ext != ".json")
303:         continue; // Not a substance file
304:       SESubstance* sub = GetSubstance(name);
305:       if (!sub->SerializeFromFile(filename))
306:       {
307:         Error("Unable to read substance " + filename);
308:         continue;
309:       }
310:     }
311:     catch (...)
312:     {
313:       Info("I caught something in " + filename);
314:       continue;
315:     }
316:   }
317: 
318:   for (auto filename : compounds)
319:   {
320:       try
321:       {
322:         // I am assuming the filename is also the substance name
323:         // If we don't want to make that assumption, we need to have
324:         // a map of filename to substance ptr and use it rather than GetSubstance by name.
325:         SplitFilenameExt(filename, name, ext);
326:         if (ext != ".json")
327:           continue; // Not a substance file
328:         SESubstanceCompound* cmpd = GetCompound(name);
329:         if (!cmpd->SerializeFromFile(filename, *this))
330:         {
331:           Error("Unable to read substance compound " + filename);
332:           continue;
333:         }
334:       }
335:       catch (...)
```