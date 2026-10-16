#!/usr/bin/env node
/**
 * Build a conservative public LinkedIn speaker cache from the packaged schedule.
 * Only exact-name matches with supporting event-headline overlap are published.
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dataApiPath = '/home/ubuntu/skills/data-api/lib/data-api.mjs';
const { ApiClient } = await import(pathToFileURL(dataApiPath).href);
const client = new ApiClient();
const schedule = JSON.parse(await fs.readFile(path.join(repo, 'data', 'schedule.json'), 'utf8'));

function normalize(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function tokens(value) {
  return new Set(normalize(value).split(' ').filter((token) => token.length >= 3 && !new Set([
    'senior', 'engineer', 'architect', 'consultant', 'community', 'builder', 'solution', 'solutions',
    'principal', 'software', 'cloud', 'lead', 'founder', 'manager', 'developer', 'specialist', 'aws',
  ]).has(token)));
}

function scoreCandidate(speaker, candidate) {
  const candidateName = normalize(candidate.fullName || '');
  const exactName = candidateName === normalize(speaker.name);
  if (!exactName) return { exactName: false, score: 0 };
  const expected = tokens(speaker.eventHeadline);
  const actual = tokens(`${candidate.headline || ''} ${candidate.summary || ''}`);
  let overlap = 0;
  for (const token of expected) if (actual.has(token)) overlap += 1;
  return { exactName, score: 60 + Math.min(30, overlap * 10) };
}

const speakers = new Map();
for (const session of schedule.sessions || []) {
  for (const speaker of session.speakers || []) {
    if (speaker.name) speakers.set(speaker.name, speaker);
  }
}

async function enrich(speaker) {
  const [firstName, ...rest] = speaker.name.split(/\s+/);
  const lastName = rest.join(' ');
  try {
    const result = await client.callApi('LinkedIn/search_people', {
      query: { keywords: speaker.name, firstName, lastName },
    });
    const candidates = result?.data?.items || [];
    const ranked = candidates
      .map((candidate) => ({ candidate, ...scoreCandidate(speaker, candidate) }))
      .filter((item) => item.exactName && item.candidate.profileURL)
      .sort((left, right) => right.score - left.score);
    const best = ranked[0];
    if (!best || best.score < 70) {
      return { name: speaker.name, status: 'not_verified' };
    }
    return {
      name: speaker.name,
      headline: String(best.candidate.headline || '').trim(),
      profileUrl: String(best.candidate.profileURL || '').trim(),
      retrievedAt: new Date().toISOString(),
      source: 'LinkedIn public profile search',
      matchScore: best.score,
    };
  } catch {
    return { name: speaker.name, status: 'not_verified' };
  }
}

const sourceSpeakers = [...speakers.values()];
const profiles = [];
const unresolved = [];
const limit = 3;
for (let index = 0; index < sourceSpeakers.length; index += limit) {
  const batch = sourceSpeakers.slice(index, index + limit);
  const results = await Promise.all(batch.map(enrich));
  for (const result of results) {
    if (result.status === 'not_verified') unresolved.push(result.name);
    else profiles.push(result);
  }
}

const output = {
  source: 'LinkedIn public profile search',
  generatedAt: new Date().toISOString(),
  matchingRule: 'Exact speaker name plus event-headline overlap; ambiguous matches excluded.',
  profiles: profiles.sort((a, b) => a.name.localeCompare(b.name)),
  unresolved: unresolved.sort(),
};
await fs.writeFile(path.join(repo, 'data', 'speaker_profiles.json'), `${JSON.stringify(output, null, 2)}\n`);
console.log(JSON.stringify({ verifiedProfiles: profiles.length, unresolved: unresolved.length }, null, 2));
