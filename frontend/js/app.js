// Boot: resolve the palette from CSS, register routes, start the router.

import { initPalette } from './core/palette.js';
import { register, start } from './core/router.js';
import { refreshHeader } from './core/header.js';
import { subscribe } from './core/store.js';

import * as overview from './pages/overview.js';
import * as graph from './pages/graph.js';
import * as playback from './pages/playback.js';
import * as analytics from './pages/analytics.js';
import * as findings from './pages/findings.js';
import * as explainer from './pages/explainer.js';

initPalette();

register('overview', overview);
register('graph', graph);
register('playback', playback);
register('analytics', analytics);
register('findings', findings);
register('explainer', explainer);

// Any page that loads fresh data refreshes the global chrome too.
subscribe(() => { refreshHeader(); });

start(document.getElementById('view'));
refreshHeader();
