# Le guide de kealeb

Tout ce que le cadriciel sait faire, dans l'ordre où vous le rencontrerez.
Une demi-heure d'un bout à l'autre. Chaque extrait ci-dessous compile ; les
versions longues sont dans [`examples/`](../examples).

*The same walkthrough in English: [`guide.md`](guide.md).*

---

## 1. Un programme

```keal
import "kealeb/kealeb.keal"

val site = app("Mon site")

site.page("/", { req -> column([
    h1("Bonjour"),
    p("depuis Keal")
])})

site.run(8080)
```

```sh
tools/build.sh bonjour.keal
build/bonjour
```

`app(titre)` crée une application. `run(port)` sert jusqu'à l'arrêt du
processus. Entre ces deux lignes, on déclare ce que le site répond.

L'import est le parapluie : tout ce guide est visible après cette ligne. Un
programme qui en veut moins importe un seul module —
`import "kealeb/src/http.keal"` amène la requête et la réponse, et rien
d'autre.

## 2. Utiliser kealeb depuis votre propre projet

Le guide, jusqu'ici, suppose que vous êtes dans ce dépôt. Ce n'est pas
obligatoire. kealeb est un paquet Keal, et un projet qui le veut le dit :

```toml
# keal.toml
[package]
name = "monprojet"
version = "0.1.0"

[dependencies]
kealeb = { git = "https://github.com/geneacta/kealeb", tag = "v0.1.0" }
```

```sh
keal fetch                                  # le met dans .keal/deps/kealeb
.keal/deps/kealeb/tools/build.sh app.keal   # la sortie va dans *votre* build/
```

```keal
import "dep:kealeb/kealeb.keal"
```

Le script de construction est la seule partie qui n'est pas simplement
`keal build`, et à cause d'un seul drapeau : la surface C de kealeb est un
en-tête, et il faut dire au compilateur où il est. Le lancer depuis la
dépendance s'en charge, et pose l'exécutable chez vous plutôt que chez elle. Si
vous préférez voir la commande entière :

```sh
keal build app.keal -I.keal/deps/kealeb/runtime
```

C'est tout. Ajoutez `-lsqlite3` quand le programme importe `src/sql.keal`, et
rien sinon : kealeb ne se lie à aucune bibliothèque tant que vous ne demandez
pas la base de données.

### Une chose à savoir sur `main`

Keal appelle `main` tout seul une fois le premier niveau exécuté. Un point
d'entrée nommé `main` ne doit donc **pas** être appelé en plus :

```keal
proc main() {
    site.run(8080)
}
                        // pas de `main()` ici — Keal s'en charge
```

Écrire les deux fait tourner tout le programme deux fois. C'est invisible tant
que le serveur bloque pour toujours dans sa boucle, et ça apparaît dès que la
boucle peut se terminer — ce que l'arrêt propre a rendu possible, et c'est
comme ça que ça a été trouvé ici.

## 3. Les routes

Cinq verbes et un attrape-tout, chacun prenant un chemin et un gestionnaire :

```keal
site.get("/sante", { req -> text("ok") })
site.post("/commandes", { req -> jsonBody("{\"id\":7}").status(201) })
site.put("/commandes/{id}", { req -> text("remplacée ${req.param("id")}") })
site.patch("/commandes/{id}", { req -> text("modifiée") })
site.delete("/commandes/{id}", { req -> noContent() })
site.any("/ping", { req -> text("pong") })
```

Un gestionnaire est un `(Request) -> Response`. C'est un type de fonction
ordinaire, donc ce peut être une fonction nommée, une lambda, ou une valeur
qu'on se passe :

```keal
func sante(req: Request): Response { return text("ok") }

site.get("/sante", sante)
site.get("/santez", sante)
```

Une fonction nommée utilisée comme valeur demande Keal en `4b21fc5` ou plus
récent. Avant cela, le backend natif émettait le pointeur de fonction nu là où
une fermeture était attendue, et le programme mourait — trouvé ici, corrigé en
amont le jour même.

### Ce qu'un motif peut dire

| motif | correspond à | `req.param(...)` |
|---|---|---|
| `/user/new` | exactement cela | — |
| `/user/{id}` | `/user/42` | `id` vaut `42` |
| `/files/{reste...}` | `/files/a/b.css` | `reste` vaut `a/b.css` |

Un `{nom...}` final attrape tout ce qui reste, barres obliques comprises, et
ne peut être que le dernier. Les segments arrivent décodés :
`/user/le%20monde` donne `req.param("id") == "le monde"`.

**Quand deux motifs correspondent, celui qui a le plus de segments littéraux
gagne.** `/user/new` l'emporte sur `/user/{id}`, quel que soit l'ordre de
déclaration. C'est la seule règle de priorité, et elle ne dépend pas de
l'ordre où vous les avez écrites.

Un chemin qui ne correspond à rien est un 404. Un chemin qui correspond sous
un autre verbe est un **405** portant `Allow:` — la différence compte pour
tous les clients, et un cadriciel incapable de la faire les oblige tous à
deviner.

## 4. La requête

```keal
site.post("/recherche", { req ->
    val q = req.queryOr("q", "")                 // ?q=…
    val page = req.queryOr("page", "1").toInt() ?: 1
    val qui = req.headerOr("user-agent", "?")    // la casse est indifférente
    val sid = req.cookie("session")              // String?
    val form = req.form()                        // un formulaire posté, décodé
    val corps = req.text()                       // le corps, en texte
    text("${q} ${page} ${qui}")
})
```

| | |
|---|---|
| `method` `path` `target` `version` `peer` | tels qu'arrivés ; `path` est décodé, `target` non |
| `param(nom)` | ce que la route a capturé — `""` si la route n'a pas ce trou |
| `query` · `queryOr(nom, défaut)` | la chaîne de requête, analysée |
| `header(nom): String?` · `headerOr` · `hasHeader` | la casse est repliée ; un en-tête envoyé deux fois arrive joint par `, ` |
| `cookies(): Map` · `cookie(nom): String?` | |
| `text()` · `form()` · `formAll()` · `body` | le corps en texte, en formulaire, en gardant les répétitions, en octets |
| `contentType()` | le type de média, sans ses paramètres |
| `keepAlive()` · `isUpgrade()` | ce à quoi sert la connexion |

Une `Request` ne se modifie pas. Keal dit que le contenu d'un paramètre
appartient à l'appelant sauf si la signature dit `var`, et un type de fonction
ne peut pas dire `var` — donc un gestionnaire reçoit la réponse plutôt que
l'occasion de changer la question. Là où le cadriciel doit ajouter quelque
chose, il en construit une nouvelle : c'est ce que fait `withParams`, et elle
partage le corps au lieu de le copier.

## 5. La réponse

```keal
html("<p>salut</p>")                     // text/html; charset=utf-8
text("brut")                             // text/plain; charset=utf-8
jsonBody("{\"ok\":true}")                // application/json
bytes("image/png", unBuf)                // n'importe quoi, depuis des octets
noContent()                              // 204
redirect("/suite")                       // 302 ; redirect("/x", 301) si permanent
notFound("commande inconnue")            // 404
badRequest("id doit être un nombre")     // 400
serverError()                            // 500
```

Chacune répond une `Response`, et chaque réglage répond de nouveau la réponse,
si bien qu'une ligne se lit d'un bloc :

```keal
html(page).status(201).type("text/html").with("x-made-by", "kealeb").cookie("sid", jeton, 3600)
```

Gardez une chaîne d'appels **sur une seule ligne**. Keal termine une
instruction au saut de ligne quand le jeton précédent pouvait en terminer une,
donc un `.` en début de ligne suivante est une nouvelle instruction, pas une
continuation.

`cookie(nom, valeur, maxAge, path, httpOnly, sameSite)` vaut par défaut
`HttpOnly`, `SameSite=Lax`, chemin `/`, et aucun `Max-Age` — ce qui veut dire
*cette session de navigateur*. `maxAge = 0` supprime.

`Content-Length` est toujours écrit d'après le nombre d'octets du corps et ne
peut pas être remplacé. Une longueur en désaccord avec son corps casse la
requête *suivante* plutôt que celle-ci : c'est un bug dont il vaut la peine de
refuser la possibilité.

## 6. Les pages

Une page est une fonction d'une requête vers un arbre de composants. Le
cadriciel l'enveloppe dans un document et l'envoie.

```keal
site.page("/a-propos", { req -> column([
    h1("À propos"),
    p("Deux paragraphes et un lien."),
    link("/", "accueil")
])}, "À propos de nous")
```

Le dernier argument est le `<title>` ; sans lui, c'est le titre de
l'application.

### L'arbre

Chaque constructeur répond un `Node`, et chaque réglage le répond de nouveau.

```keal
el("section").cls("hero").id("haut").attr("role", "banner").add(h1("Titre"))
```

| | |
|---|---|
| `el(balise)` · `elt(balise, enfants)` | n'importe quel élément |
| `txt(s)` | du texte — **toujours échappé** |
| `raw(s)` | du balisage déjà balisé, et qui doit être exactement un élément |
| `nothing()` | un nœud qui occupe une place et ne montre rien |
| `div` `span` `p` `h1` `h2` `h3` `strong` `em` `code` `pre` `br` `hr` | |
| `link(href, s)` · `img(src, alt)` | |
| `ul` `ol` `li` · `table` `thead` `tbody` `tr` `th` `td` `tdt` | |
| `section` `header` `footer` `nav` `main` | |
| `form` `label` `option` | |
| `.cls(noms)` `.id(v)` `.style(v)` `.title(v)` `.attr(n, v)` `.flag(n, oui)` | |
| `.add(enfant)` `.addAll(enfants)` `.on(événement, gestionnaire)` `.keyed(k)` | |

`.flag(nom, oui)` sert aux attributs booléens : il écrit `disabled` quand
`oui` et l'omet sinon, parce que `disabled="false"` désactive quand même.

### Les composants

`row`, `column` et `card` sont de la mise en page ; les autres prennent des
gestionnaires et ne signifient quelque chose que sur une page vivante.

```keal
row([button("Enregistrer", { e -> sauver() }), button("Annuler", { e -> retour() })])
column([field(nom, { e -> nom = e.value }), checkbox(actif, { e -> actif = e.checked() })])
select(choisi, [("a", "Alpha"), ("b", "Bêta")], { e -> choisi = e.value })
textarea(corps, { e -> corps = e.value })
shownWhen(n > 0, p("${n} en attente"))
```

`submit(texte)` est l'autre espèce : un bouton qui soumet son formulaire de
façon ordinaire, pour une page qui fonctionne sans aucun JavaScript.

### Des styles écrits en Keal

`.style("color: red")` prend une chaîne et le fera toujours — pour une
déclaration sur un nœud, c'est la chose la plus courte et la plus honnête. Pour
une feuille entière, `css.keal` en construit une à partir de valeurs :

```keal
val href = site.css(sheet([
    vars(":root", [("--accent", "#2f6feb")]),
    rule(".hero").bg("var(--accent)").fg("white").pad("3rem 2rem").radius("12px"),
    rule(".hero h1").size("2.4rem").weight("700"),
    media("(max-width: 600px)", [rule(".hero").pad("1.5rem")])
]))
```

| | |
|---|---|
| `rule(sélecteur)` | une règle ; chaque réglage la répond, donc on chaîne ou pas |
| `.set(propriété, valeur)` | celui qui marche toujours |
| `.fg` `.bg` `.pad` `.margin` `.border` `.radius` `.font` `.size` `.weight` `.width` `.height` `.gap` `.display` `.flex` `.grid` `.shadow` `.opacity` `.cursor` `.position` `.overflow` `.transition` | ceux qui méritent un nom |
| `media(requête, règles)` · `supports(requête, règles)` | les at-rules ; la requête est le sélecteur |
| `vars(sélecteur, paires)` | les propriétés personnalisées, en une règle |
| `sheet(règles)` | le tout, en texte |

Ce n'est pas un analyseur CSS et rien n'est validé : ce que vous écrivez sort.
Ce que ça achète, c'est qu'**une règle est une valeur** — tenue dans une liste,
rendue par une fonction, construite par une boucle — et que les sélecteurs et
les nombres viennent du même endroit que le reste du programme.

`site.css(texte)` la sert et la lie depuis chaque page. L'URL nomme le contenu
— `/kealeb/asset-2b7c19f4e1.css` — donc elle part avec un cache d'un an
`immutable` et change à l'instant où la feuille change. Elle répond cette URL,
pour une page qui voudrait la référencer elle-même.

### Le JavaScript, et quand il en faut

```keal
site.script("/* une carte, un graphique, une balise de mesure */")
site.linkStyle("https://fonts.example/chose.css")
site.inHead("<link rel=\"icon\" href=\"/favicon.svg\">")
```

`script` est servi et mis en cache de la même façon, avec `defer`. Tout l'intérêt
du cadriciel est que vous n'en ayez pas besoin — les événements et le rendu sont
du Keal, sur le serveur. C'est là pour ce qui appartient vraiment au navigateur.
Si vous vous surprenez à y écrire de la logique applicative, le cadriciel a
échoué sur quelque chose et il vaut la peine de dire sur quoi.

**L'ordre n'a pas d'importance.** Le titre, la feuille de style et les
ressources sont figés à la construction du serveur, donc après tous les
enregistrements : une page déclarée avant `site.css(...)` reçoit quand même la
feuille. C'était un vrai défaut, et cette phrase dit qu'il n'en est plus un.

### L'échappement

`txt` échappe. Il n'y a pas de drapeau pour l'en empêcher — `raw` est une
autre fonction, avec un autre nom, et c'est toute l'histoire de la sécurité
ici. Les valeurs d'attribut sont en plus échappées pour les guillemets.

### La feuille de style

Chaque page charge `/kealeb/kealeb.css` : une centaine de lignes, chaque règle
préfixée `kb-`, suivant le mode sombre du système. Pour mettre la vôtre :

```keal
site.style = "/static/app.css"     // la vôtre à la place
site.style = ""                    // aucune
site.head = "<link rel=\"icon\" href=\"/favicon.svg\">"
```

## 7. Les formulaires sans JavaScript

```keal
site.page("/saluer", { req -> column([
    h1("Saluer"),
    el("form").attr("method", "post").add(row([
        el("input").cls("kb-input").attr("name", "nom"),
        submit("Dire bonjour")
    ]))
])})

site.post("/saluer", { req ->
    val nom = req.form().get("nom") ?: ""
    html(doc("Saluer", h1("Bonjour, ${nom}")))
})
```

Rien ici n'a besoin de socket, de session ni de script. C'est toute la
troisième route de [`examples/hello.keal`](../examples/hello.keal).

### Les fichiers

Un formulaire qui porte un fichier poste du `multipart/form-data`, ce sont des
octets et non du texte — un PNG passé dans un validateur UTF-8 est un PNG
corrompu. C'est donc analysé sur les octets, et une `Part` vous rend l'un ou
l'autre.

```keal
site.post("/upload", { req ->
    val doc = req.file("doc")
    if (doc == null) {
        badRequest("choisissez un fichier")
    } else {
        doc.saveTo("uploads/${epochS()}-${doc.safeName()}")
        redirect("/", 303)
    }
})
```

| | |
|---|---|
| `req.isMultipart()` | est-ce ce genre de corps ? |
| `req.parts()` | toutes les parties, dans l'ordre |
| `req.part(nom)` | une partie, ou null |
| `req.file(nom)` | une partie, mais **seulement** si un fichier a vraiment été choisi |
| `p.name` `p.filename` `p.kind` | le nom du champ, le nom du fichier côté client, le type prétendu |
| `p.text()` `p.bytes()` `p.size()` `p.isFile()` | |
| `p.saveTo(chemin)` · `p.safeName(défaut)` | |

Trois choses à savoir avant d'écrire le gestionnaire :

* **`file` et `part` ne posent pas la même question.** Un navigateur envoie une
  partie pour un champ fichier même quand personne n'a choisi de fichier — nom
  vide, contenu vide. `part` vous la donne ; `file` répond `null`, ce qui est
  la vérification que tout gestionnaire d'envoi oublierait sinon.
* **`kind` est une affirmation.** Le client dit ce qu'il veut. Un serveur qui
  le croit est un serveur qui sert un script comme une image.
* **`filename` n'est jamais un chemin.** C'est ce qu'un inconnu a tapé,
  `../../etc/` compris. `saveTo` prend un chemin que *vous* avez choisi, et il
  n'y a délibérément pas de `save(dansCeRépertoire)` : cette fonction devrait
  décider quoi faire du nom du client, et chaque mauvaise réponse est un
  répertoire dont quelqu'un est sorti. `safeName()` le réduit aux lettres,
  chiffres et `. - _`, et cela reste un nom choisi par un inconnu : servez-vous
  en pour montrer à quelqu'un ce qu'il a envoyé, et générez le nom que vous
  rangez.

Tout le corps est en mémoire, borné par le `maxBody` du serveur (8 Mo par
défaut). Pas d'écriture au fil de l'eau, pas de `multipart/mixed`, et pas de
`Content-Transfer-Encoding` autre que l'identité — un navigateur qui poste un
formulaire n'envoie rien de tout cela.

## 8. Les pages vivantes

```keal
site.livePage("/", { req ->
    var compte = 0
    view({ -> column([
        h1("Cliqué ${compte} fois"),
        button("Cliquez-moi", { e -> compte = compte + 1 })
    ]) })
})
```

Deux fonctions, et la différence entre les deux est tout le modèle :

* **L'extérieure s'exécute une fois par visiteur.** Ce qu'elle capture est
  l'état de ce visiteur-là. Il n'y a pas de table de sessions à indexer
  correctement — la fermeture *est* la session.
* **L'intérieure s'exécute après chaque événement.** Elle doit être une
  fonction de l'état et de rien d'autre : ce qu'elle lit et qui peut changer
  sans événement ne sera pas remarqué avant le suivant.

### Ce qui se passe

1. Le navigateur demande la page. Le serveur construit l'arbre, numérote les
   nœuds qui écoutent, envoie le HTML, et garde l'arbre.
2. Un petit script ouvre un WebSocket vers `/kealeb/live`.
3. Vous cliquez. Le script envoie
   `{"i":"0.2.1","e":"click","v":"","f":{}}` — quel nœud, quel événement, ce
   qu'il contenait.
4. Le serveur exécute le gestionnaire, reconstruit l'arbre, le compare à celui
   qu'il avait gardé, et envoie la différence.
5. Le script l'applique. Six opérations existent et il n'y en a pas de
   septième : changer le texte d'un nœud texte, poser un attribut, retirer un
   attribut, remplacer un nœud, insérer un enfant, retirer un enfant.

Un gestionnaire est un `(Ev) -> Unit` :

| | |
|---|---|
| `e.name` | `click`, `input`, `change`, `submit`, `keydown` |
| `e.value` | ce que l'élément contenait — le texte du champ, `"true"`/`"false"` pour une case, l'option choisie |
| `e.number(défaut)` · `e.checked()` | la valeur, lue |
| `e.field(nom)` | un champ du formulaire sur `submit`, la touche sur `keydown` |

### La règle unique

**Un `Node`, un nœud dans le navigateur.** L'identité d'un nœud est sa
position — `0.2.1`, comptée depuis le point de montage — donc tout ce qui ne
rendrait aucun octet décalerait tout ce qui suit. C'est pour cela que
`nothing()` existe et rend un commentaire vide, et pour cela que `raw` doit
contenir exactement un élément.

### L'identité, et quand dire ce qu'un nœud est

Sans clé, **l'identité est la position**. Le nœud en `0.2.1` est comparé à ce
qui était en `0.2.1` la fois d'avant, et si les balises correspondent, le nœud
du navigateur est conservé et ses attributs ajustés. C'est juste quand c'est la
même chose rendue de nouveau — le cas ordinaire, soixante fois sur soixante.

C'est faux quand deux choses *différentes* atterrissent au même endroit : une
liste décalée d'un cran, un onglet qui a changé, une ligne supprimée. Le nœud
est conservé, et avec lui tout ce que le serveur ignore de lui — le caret, le
focus, la position de défilement, une frappe pas encore signalée. Tout cela
appartient maintenant à autre chose.

`.keyed(id)` est la façon pour une page de dire *ceci est une autre chose* :

```keal
for (tache in taches) {
    lignes.add(row([...]).keyed("tache-${tache.id}"))
}
```

Un nœud dont la clé a changé est reconstruit plutôt que rapiécé, si bien que
cet état part avec lui. Les clés sont comparées sur le serveur et n'atteignent
jamais le navigateur.

Ce que les clés ne font **pas** encore, c'est rendre un déplacement bon marché :
insérer en tête d'une liste réécrit toujours tout ce qui suit, parce que le
diff parcourt les enfants par indice et ne cherche pas celui qui a bougé.
Correct, et plus de travail qu'il n'en faut. C'est la prochaine chose à
corriger.

### Les sessions

Une session vit aussi longtemps que son socket, plus `ttlMs` (une minute par
défaut) pour l'onglet qui s'est endormi. Une page dont le serveur a oublié la
session se recharge elle-même et en obtient une nouvelle.

```keal
site.live.ttlMs = 300000        // cinq minutes
site.live.size()                // combien de pages sont ouvertes
site.live.refreshAll()          // reconstruire toutes les pages ouvertes
```

`refreshAll` est ce qu'on appelle quand le monde a changé sous toutes à la
fois — une ligne insérée par autre chose, une tâche terminée.

### Ce que cela coûte

Le serveur garde une session par page ouverte. Une page ouverte est de la
mémoire utilisée. C'est le marché de Vaadin et c'est celui que kealeb passe ;
si une page doit tenir cent mille onglets inactifs, ce doit être une `page` et
non une `livePage`.

## 9. Les fichiers statiques

```keal
site.files("/static", "./public")      // /static/a/b.css -> ./public/a/b.css
site.file("/favicon.svg", "./public/favicon.svg")
```

Chaque réponse porte un `ETag` fait de la date et de la taille du fichier, et
un client qui le renvoie obtient un 304 sans corps.

Tout chemin comportant un segment `..`, une barre initiale, une barre inverse
ou un composant caché est un **403** — refusé, pas normalisé. Normaliser un
chemin hostile, c'est ainsi qu'on sort d'un répertoire.

## 10. JSON

```keal
val champs: Map<String, Json> = {}
champs.set("id", jInt(7))
champs.set("nom", jStr("Ada"))
champs.set("etiquettes", jStrs(["a", "b"]))
jsonBody(jObj(champs).write())
```

À la lecture :

```keal
site.post("/commandes", { req ->
    val corps = parseJson(req.text())
    if (corps == null) { badRequest("ce n'est pas du JSON") } else {
        text("id ${corps.intAt("id")} pour ${corps.str("nom")}")
    }
})
```

`parseJson` répond un `Json?`. Du texte en trop est un refus, pas quelque
chose à ignorer. `field(nom)` répond un `Json?`, ce qui n'est pas la même
chose qu'un champ dont la valeur est `null` en JSON — et c'est pour cette
différence qu'il est nullable.

## 11. Les tests

Un gestionnaire est une fonction, donc l'essentiel d'un site se teste sans
aucun socket :

```keal
val r = Router()
r.get("/user/{id}", { req -> text("user ${req.param("id")}") })

assert(dispatch(r, request("GET", "/user/42")).text() == "user 42", "le paramètre")
assert(dispatch(r, request("GET", "/rien")).code == 404, "et rien d'autre")
```

`request(méthode, cible)` en construit une à la main. `dispatch(router, req)`
la passe dans la table.

Quand on veut vraiment le socket, on demande le port 0 et la machine en
choisit un :

```keal
val s = site.serverOn(0)
val port = s.open()          // le port réellement obtenu
s.tick(50)                   // un tour de boucle
```

`tools/test.sh` lance [`tests/units.keal`](../tests/units.keal) et, si `node`
est présent, [`tests/client.mjs`](../tests/client.mjs) — qui exécute le vrai
script client contre un vrai serveur.

### Tester ce qu'un programme laisse derrière lui

Keal libère un objet quand sa dernière référence disparaît, donc une fuite ici
est un **cycle** et rien d'autre. `keal build --audit` dit ce qui a survécu au
programme et lequel n'était plus joignable :

```sh
keal build --audit tests/lifetime.keal && ./lifetime
```

Le piège est que le verdict arrive *après* la dernière instruction : le
programme ne peut donc pas l'affirmer lui-même — quand la réponse existe, il
n'y a plus de programme pour en faire quelque chose. Il faut que quelque chose
d'extérieur lise la sortie ; `tools/test.sh` le fait, et échoue avec le rapport
entier quand la réponse n'est pas `nothing outlived the program`. Une version
de ce test finissant par `assert(true, "aucune fuite")` ressemble à un test,
passe au vert pour toujours, et ne vérifie rien.

Ce test affirme un négatif, il a donc un témoin :
[`tests/leaks.keal`](../tests/leaks.keal) construit le cycle exprès, et le
lanceur exige que l'audit le voie encore, et qu'il en voie exactement un. Une
suite qui ne vérifie jamais que l'absence d'une chose passe au vert le jour où
elle cesse de savoir la trouver.

La règle tient en une ligne et ne parle ni de gestionnaires ni de kealeb :
**une fermeture rangée dans un objet ne doit pas tenir cet objet.** Le comptage
de références libère ce que plus rien ne désigne, et une boucle se désigne
elle-même.

Dans ce cadriciel la boucle passe par le routeur — il tient le gestionnaire, et
l'application le tient — donc la forme à éviter est un gestionnaire qui revient
à l'application :

```keal
val site = app("le mien")

site.get("/a", { req -> text(site.title) })       // tient l'application
val nom = site.title
site.get("/b", { req -> text(nom) })              // tient une chaîne
```

Dans une méthode de votre propre classe, c'est la même chose épelée `this`.
Dans les deux cas le remède est le même : lire ce dont la fermeture a besoin
dans un local *avant* la lambda, et la fermeture tient la valeur au lieu de
l'objet qui l'avait.

Dans un programme ordinaire cela ne coûte rien, et il vaut mieux le dire
franchement que crier au loup : `val site = app(...)` au premier niveau vit
jusqu'à la fin du processus, donc une boucle à l'intérieur n'est jamais
ramassée parce que rien n'allait jamais la ramasser. Cela compte quand une
application est construite puis lâchée — un test, ou un programme qui en sert
plusieurs. C'est précisément ce que fait `tests/lifetime.keal`, et pourquoi ses
gestionnaires ne mentionnent jamais `site`.

`weak` n'est pas la réponse ici : ce serait dire que l'application n'est que
faiblement tenue par ses propres routes, ce que le programme ne veut pas dire.

## 12. Les filtres

Un filtre enveloppe chaque requête. C'est une fonction ordinaire : pas de
registre, pas d'annotation d'ordre, pas de configuration de chaîne — l'ordre
est celui dans lequel vous les avez écrits.

```keal
site.use({ req, next ->
    val debut = monoMs()
    val res = next.on(req)
    println("${req.method} ${req.path} ${res.code} ${monoMs() - debut}ms")
    res
})
```

Ils s'exécutent **du plus extérieur au plus intérieur** et se déroulent dans
l'autre sens, donc le premier ajouté est le dernier à voir la réponse. Un
filtre qui n'appelle jamais `next.on(req)` a répondu lui-même, et c'est à quoi
ressemble un refus :

```keal
site.use({ req, next ->
    if (req.path.startsWith("/admin") and (not a.signedIn(req))) {
        redirect("/sign-in", 303)
    } else {
        next.on(req)
    }
})
```

Les filtres sont **à l'intérieur** de ce qu'installe `secure` et **à
l'extérieur** du routeur : un filtre ne voit jamais une requête qui a raté son
contrôle CSRF, et tout ce qu'un filtre répond reçoit quand même les en-têtes.

Un filtre est tenu par l'application, donc la règle qui vaut partout ailleurs
vaut ici : un filtre ne doit pas capturer l'application. Lisez ce dont il a
besoin dans un local d'abord.

Quand une seule fonction suffit, `Server.handle` est toujours là, et le
remplacer remplace tout, routage compris.

## 13. La mise en service

```keal
site.run(8080)                        // 127.0.0.1 — ne peut surprendre personne
site.run(8080, "")                    // toutes les interfaces
site.log = false                      // pas de ligne par requête
```

Le serveur qu'elle construit se règle avant de démarrer :

```keal
val s = site.serverOn(8080)
s.maxHead = 16 * 1024                 // au-delà, c'est 431
s.maxBody = 2 * 1024 * 1024           // au-delà, c'est 413
s.idleMs = 15000                      // une connexion silencieuse est fermée
s.maxRequests = 500                   // par connexion, puis on ferme
s.handle = { req -> monPropreAiguillage(req) }
s.run()
```

Il n'y a pas de TLS. Mettez-le derrière un proxy inverse, qui est la place
d'un terminateur ; `X-Forwarded-For` arrive comme un en-tête ordinaire et
`req.peer` est le proxy.

La sortie standard est tamponnée par lignes dès le démarrage du serveur, donc
un journal redirigé vers un fichier ou un superviseur arrive au fil de
l'écriture.

### L'arrêt

`SIGINT` et `SIGTERM` — Ctrl-C, et ce qu'envoie un gestionnaire de services —
ne tuent plus le processus. Ils lui demandent de s'arrêter, et il le fait dans
cet ordre :

1. `onStop` s'exécute, si vous en avez posé un.
2. L'écouteur se ferme, donc un client qui se connecte maintenant est refusé
   par le noyau et peut aller ailleurs.
3. Les connexions au milieu d'une réponse ont jusqu'à `drainMs` (cinq
   secondes) pour finir. Celles qui ne doivent rien sont fermées tout de
   suite — attendre un keep-alive inactif reviendrait à attendre le délai
   entier à chaque fois.
4. Ce qui reste ouvert après est fermé quand même, avec une ligne qui le dit.
   Un arrêt qui attend pour toujours est un processus que quelqu'un doit tuer,
   et être tué est précisément ce que ceci évite.

```keal
val s = site.serverOn(8080)
s.onStop = { -> println("au revoir") }
s.drainMs = 15000
s.run()
```

Un gestionnaire ne peut pas être interrompu, donc une requête déjà en cours va
toujours jusqu'au bout : le signal pose un drapeau et c'est la boucle qui le
remarque — ce qui est aussi la seule chose qu'on ait le droit de faire dans un
gestionnaire de signal.

### Quand il n'y a rien, et quand quelque chose a cassé

```keal
site.onNotFound({ req -> column([h1("Rien à ${req.path}"), link("/", "accueil")]) })
site.onError({ req -> column([h1("Quelque chose a mal tourné"), p("C'est noté.")]) })
```

Les deux construisent une page comme n'importe quelle autre — le document, la
feuille de style, la forme du site — et les deux ne remplacent la réponse que
**si le client a demandé du HTML**. Le 404 d'une API reste la phrase courte
qu'un programme peut lire, parce qu'une gestion d'erreur qui doit analyser du
HTML est une gestion d'erreur que personne n'écrit.

`onError` ne reçoit pas ce qui a été levé, exprès. Ce qu'un gestionnaire a levé
peut contenir une requête, un chemin, un mot de passe — tout ce qu'il tenait au
moment d'abandonner — donc cela part sur la sortie standard, où quelqu'un qui
peut lire le journal peut le lire, et un journal n'est pas une chose qu'un
inconnu peut lire.

Le `try` qui transforme une exception en 500 est **à l'intérieur** des filtres,
autour du routeur. Ce n'est pas un détail : un gestionnaire qui lève déroule
tous les filtres qui l'entourent en sortant, donc un `try` plus à l'extérieur
produirait un 500 qu'aucun filtre ne voit — `onError` ne pourrait pas le
remplacer, et un filtre de journalisation manquerait précisément la requête
qu'il fallait noter.

## 14. Le travail programmé

```keal
site.every(60000, { -> viderLesPaniersExpires() })   // chaque minute
site.after(5000, { -> prechaufferLeCache() })        // une fois, cinq secondes après
```

Une tâche s'exécute sur le fil de la boucle, **entre deux requêtes et jamais
pendant une**, donc elle lit et écrit ce qu'un gestionnaire lit et écrit sans
rien à synchroniser — pas de verrou, pas de file, pas de copie. C'est le même
marché que le reste du cadriciel, et il a le même prix : une tâche qui bloque
bloque le serveur.

Une tâche plus longue que son intervalle tourne simplement moins souvent
qu'elle ne l'a demandé. Elle n'est jamais lancée deux fois, et il n'y a pas de
file d'exécutions manquées prête à se ruer quand elle finit.

Une tâche qui lève une exception est signalée sur la sortie standard et
**garde son rythme** — un traitement qui échoue une fois par heure doit quand
même être retenté l'heure suivante, et un serveur qui meurt parce qu'un
traitement a échoué est pire que le traitement qui échoue.

Depuis un serveur qu'on tient déjà, `every` et `after` répondent le `Timer`,
qu'on peut annuler (`cancel()`) ou faire tourner tout de suite (`soon()`) :

```keal
val s = site.serverOn(8080)
val battement = s.every(30000, { -> ping() })
battement.soon()                                     // au prochain tour
battement.cancel()                                   // et plus jamais
```

Le coût est une comparaison par tour de boucle et rien d'autre : la boucle
dormait déjà dans `poll` avec une échéance, et un minuteur est cette échéance
choisie au lieu d'être supposée. Un serveur sans tâche dort exactement comme
avant.

La règle sur ce qu'une tâche peut capturer est celle des gestionnaires : **une
tâche ne doit pas tenir l'application.** `site.every(1000, { -> println(site.title) })`
ferme la boucle que `tests/lifetime.keal` existe pour garder ouverte.

Il n'y a ni expression cron ni calendrier. `every` compte des millisecondes.
Une tâche qui doit tourner à 03:00 doit regarder l'horloge elle-même —
`utcNow()` est dans le prélude — parce qu'un ordonnanceur qui comprend les
fuseaux et l'heure d'été est un autre programme que celui-ci, et prétendre le
contraire est la façon dont un traitement tourne deux fois en octobre.

## 15. Une base de données

SQLite, et c'est un **second import et un second drapeau de liaison** — un
programme qui n'ouvre jamais de base ne doit pas se lier à une :

```keal
import "kealeb/kealeb.keal"
import "kealeb/src/sql.keal"
```

```sh
tools/build.sh app.keal -lsqlite3
```

```keal
val db = openDb("notes.db")          // ":memory:" pour un test
if (db == null) { println("impossible à ouvrir"); exit(1) }

db.migrate([
    "create table note(id integer primary key, body text not null, done integer not null default 0)",
    "alter table note add column made integer not null default 0"
])

db.run("insert into note(body) values (?)", [vText(quoi)])
for (r in db.query("select id, body, done from note order by id", [])) {
    println("${r.int("id")} ${r.text("body")} ${r.bool("done")}")
}
```

### La règle unique

**Tout ce qu'une requête peut atteindre entre comme valeur liée** — un `?`
dans le SQL, un `Val` dans la liste. Il n'existe ici aucune fonction qui
construise du SQL à partir d'une chaîne qu'on vous a envoyée, parce qu'il n'en
existe pas de version sûre à proposer.

`script()` est la seule fonction qui prenne du SQL sans paramètres. Elle est
pour le schéma que vous avez écrit, elle enchaîne plusieurs instructions, et
elle s'épelle autrement que `run` exprès. Ne lui donnez jamais rien qu'une
requête ait touché.

Deux autres refus en découlent, et tous deux sont la forme que prend une
modification laissée à moitié :

* `run` et `query` prennent **une** instruction. `"select 1; drop table note"`
  est refusé avec ces mots-là, ni exécuté ni tronqué en silence.
* Le nombre de valeurs doit correspondre au nombre de `?`. Un écart est refusé
  en nommant les deux comptes, plutôt que de devenir un `null` dans une colonne
  trois semaines plus tard.

### La lecture

| | |
|---|---|
| `db.run(sql, params)` | lignes changées, ou -1 |
| `db.query(sql, params)` | toutes les lignes, en liste |
| `db.one(sql, params)` | la première `Row?`, ou null |
| `db.value(sql, params)` | la première colonne de la première ligne, en `Val` |
| `db.script(sql)` | des instructions sans paramètres — votre schéma |
| `db.changed()` · `db.lastId()` · `db.error()` | |

Une `Row` se lit par nom — `r.int("id")`, `r.text("body")`, `r.float("score")`,
`r.bool("done")`, `r.isNull("x")` — et un nom qu'aucune colonne ne porte répond
null plutôt que d'échouer : une requête et son lecteur divergent dans le même
commit assez souvent pour qu'un plantage là n'aide personne.

Les valeurs se convertissent comme SQLite les convertit : demander son texte à
un nombre donne ses chiffres. `isNull` est séparé de tous les défauts, parce
qu'*absent* et *zéro* ne sont pas la même réponse.

Construction : `vInt` `vFloat` `vText` `vBool` `vNull`. SQLite n'a pas de
booléen, donc `vBool` est un entier qui dit lequel.

### Les transactions

```keal
db.transaction({ ->
    db.run("update compte set solde = solde - ? where id = ?", [vInt(n), vInt(de)])
    db.run("update compte set solde = solde + ? where id = ?", [vInt(n), vInt(vers)])
    true                                  // false annule
})
```

Elle valide quand le bloc répond `true`, annule quand il répond `false`, et
annule **puis relance** quand il lève — parce qu'une transaction laissée
ouverte par une exception est ce qui verrouille la base pour tout le monde.

### Les migrations

`migrate(étapes)` est la liste de toutes les migrations que le programme a
jamais eues, dans l'ordre et jamais réordonnée. L'étape 1 est `étapes[0]` ; une
base en version 2 repart de `étapes[2]`. SQLite garde le numéro dans le
fichier, donc il n'y a aucune table à créer et rien à tenir synchronisé.

Chaque étape tourne **dans une transaction avec son propre changement de
version**, donc une étape qui échoue laisse la base exactement où elle était.
Elle répond la version atteinte, ou -1 avec la raison dans `error()`.

### Ce que ce n'est pas

Il n'y a pas de mapping objet-relationnel, et il n'y en aura pas par accident.
Une `Row` est une `Row` et non votre record, parce que passer de l'une à
l'autre fait trois lignes lisibles, alors qu'un mapper qui le fait pour vous
est un second langage à apprendre avant la première requête.

Les limites honnêtes, toutes réelles :

* **Une connexion.** Le serveur est un fil ; une seconde connexion passerait sa
  vie à attendre la première. `Db` se ferme quand sa dernière référence
  disparaît, donc pas de pool à régler et rien à retenir.
* **`query` lit toutes les lignes en mémoire**, d'un coup. Une requête qui
  pourrait en rendre un million doit dire `limit`. C'est énoncé plutôt que
  caché derrière un curseur qui a l'air paresseux et ne l'est pas.
* **Pas de blobs.** Une colonne `BLOB` lue par `text()` revient avec tout ce
  qui n'est pas de l'UTF-8 bien formé changé en U+FFFD — le même traitement que
  les octets d'une socket. Lisez `kind` d'abord si la colonne peut ne pas être
  du texte.
* **SQLite seulement.** Postgres, ce serait `libpq` par la même porte C, ou son
  protocole écrit en Keal — un projet à part entière dans les deux cas.

[`examples/notes.keal`](../examples/notes.keal) est une page vivante dont
l'état est une base : arrêtez-la, relancez-la, les notes sont là. Elle montre
aussi la seule chose qu'une page vivante ne peut pas deviner —
`site.live.refreshAll()` dans un minuteur, pour qu'une page apprenne un
changement qu'elle n'a pas causé.

## 16. La sécurité

Quatre idées, et il n'y en a pas de cinquième. Un **mot de passe** stockable,
une **session** qui est un cookie signé et rien sur le serveur, une **garde**
qui est une fonction ordinaire enveloppant un gestionnaire, et un **jeton** qui
fait qu'un formulaire ne marche que s'il vient de votre page.

Pas de hiérarchie de rôles, pas de langage d'expressions, pas de chaîne de
filtres, pas d'annotations. Un rôle est une chaîne. Une règle est une fonction.

```keal
import "kealeb/src/auth.keal"

val a = auth(secretFromFile("app.secret"))
site.secure(a)
```

Ces deux lignes allument quatre choses que personne ne devrait avoir à écrire :

* chaque formulaire de chaque page reçoit un jeton CSRF caché, posé par le
  cadriciel en parcourant l'arbre ;
* chaque `POST`, `PUT`, `PATCH` et `DELETE` est refusé sans lui ;
* chaque réponse porte `nosniff`, `Referrer-Policy`, `X-Frame-Options` et une
  politique de contenu `default-src 'self'` sans place pour du script inline ;
* une bascule WebSocket dont l'`Origin` est un autre site est refusée.

Il n'y a rien à configurer parce qu'il n'y a rien là-dedans que quelqu'un
devrait vouloir éteindre. Ce qui reste à décider est ce qu'une application doit
vraiment décider : qui peut se connecter, et ce qu'il peut faire ensuite.

### Le secret

Tout est une signature sous une clé, donc un programme qui la code en dur dans
un dépôt public n'a aucune sécurité, et un programme qui en génère une neuve à
chaque démarrage déconnecte tout le monde à chaque déploiement.

```keal
val a = auth(secretFromFile("app.secret"))
```

Trente-deux octets aléatoires, faits au premier lancement, relus à tous les
suivants. **Gardez ce fichier hors du contrôle de version et sauvegardez-le** :
il signe chaque session et poivre chaque mot de passe, donc le perdre
déconnecte tout le monde *et* rend chaque empreinte stockée invérifiable.

### Les mots de passe

```keal
val stored = a.hashPassword(quoi)                 // pbkdf2-sha256$25000$…$…
if (a.checkPassword(quoi, stored)) { … }
if (a.needsRehash(stored)) { ranger(a.hashPassword(quoi)) }
```

PBKDF2-HMAC-SHA256, écrit en Keal dans `src/hash.keal` et vérifié contre les
vecteurs publiés à chaque construction. Un sel neuf de seize octets par mot de
passe, et le nombre de tours rangé à côté — donc l'augmenter plus tard
n'invalide rien, et `needsRehash` dit quand réécrire au nouveau compte.

**Pourquoi 25 000 tours et non les 600 000 que demande l'OWASP**, puisque
l'écart compte et que le cacher serait pire que de l'avoir : ce serveur est un
fil, donc hacher bloque toutes les autres requêtes le temps que ça prend.
25 000 coûtent environ 95 ms ici — mesuré, pas deviné. Au chiffre de l'OWASP,
une connexion tiendrait la boucle deux secondes et demie, et dix connexions
seraient un déni de service à la portée de n'importe qui.

Trois choses portent le poids que le nombre de tours ne porte pas :

* **Un poivre.** Chaque mot de passe est haché avec un secret qui n'est pas
  dans la base. Une base volée n'est pas quelque chose contre quoi on peut
  deviner, quel que soit le nombre de tours, à moins que le secret n'ait fui
  aussi.
* **Une limite de débit.** `a.mayTry(clé)` autorise dix tentatives par minute
  et par clé. Appelez-la avec le nom du compte *et* avec le pair, pour qu'un
  compte ne puisse pas être bloqué depuis ailleurs et qu'une machine ne puisse
  pas parcourir une liste de noms.
* **Le dire.** Si votre serveur a du temps, `a.rounds = 100000` est une ligne,
  et elle coûte ce que la mesure dit qu'elle coûte.

### Les sessions

```keal
a.signIn(redirect("/", 303), nom)       // pose le cookie
a.signOut(redirect("/", 303))           // le supprime
a.userOf(req)                           // String?, ou null
a.signedIn(req)                         // Bool
```

Toute la session est le cookie : un nom et la seconde où il a été émis, signés.
`HttpOnly`, `SameSite=Lax`, et `Secure` sauf si vous l'éteignez pour localhost.

Il n'y a pas de table, donc rien n'expire côté serveur et rien ne grossit — et
se déconnecter supprime un cookie, ce qui veut dire qu'un cookie volé reste bon
jusqu'à son expiration. C'est le marché d'une session sans état, énoncé plutôt
qu'enterré, et `a.ttl` en est le bouton (une semaine par défaut ; 0 signifie
jusqu'à la fermeture du navigateur).

### Les gardes

```keal
site.get("/prive", requireUser(a, { req -> … }))
site.get("/admin", requireWhen(a, { qui -> estAdmin(db, qui) }, { req -> … }))
```

`requireUser` envoie un inconnu vers `a.signInPath` avec `?next=` nommant où il
allait, ou répond 401 quand `signInPath` est vide — ce que veut une API et pas
un navigateur. `requireWhen` reçoit le nom et répond s'il a le droit ;
quelqu'un de connecté mais non autorisé reçoit **403**, pas 404.

Relire `?next=` est `nextAfter(req)`, et la vérification est tout l'intérêt :
une redirection qui suit une valeur qu'un inconnu contrôle est la façon dont un
lien d'hameçonnage emprunte votre domaine. Tout ce qui n'est pas un chemin
enraciné sur une seule barre est refusé, `//evil.example` compris — c'est celui
qu'on oublie.

### Le jeton

`site.secure(a)` pose un champ caché dans chaque formulaire construit par
`page` ou `livePage` dont la méthode change quelque chose, et refuse chaque
requête non sûre qui ne l'a pas. Une API peut l'envoyer comme
`X-CSRF-Token` à la place.

Le jeton est dérivé de la session plutôt que rangé, donc il ne demande aucun
état et ne peut pas se désynchroniser, et un visiteur sans session en reçoit
quand même un — ce dont le formulaire de connexion a besoin, puisqu'il doit
marcher avant que quiconque soit connecté.

Une lacune à connaître : un gestionnaire qui construit son propre document avec
`doc(...)` plutôt que par `page` n'est pas parcouru, donc ajoutez-y
`a.csrfInput(req)` vous-même. Le motif qui évite la question est
POST-puis-redirection, que vous voulez de toute façon.

### Ce que cela ne fait pas

* Ni OAuth, ni SAML, ni LDAP, ni OpenID. Un mot de passe et un cookie.
* Aucun modèle de permissions. `requireWhen` vous donne un nom et prend un
  `Bool` ; où vivent les rôles et ce qu'ils veulent dire regarde votre
  programme.
* Pas de TLS. Mettez-le derrière un proxy inverse — et tant que ce n'est pas
  fait, `a.secure = false` ou le cookie ne partira pas du tout.
* Pas de récupération de compte, pas de confirmation par courriel, pas de
  second facteur.
* **La cryptographie est écrite à la main.** `src/hash.keal` le dit en tête et
  dit pourquoi : l'alternative était de lier OpenSSL, ce qui fait une chose de
  plus à installer et une seconde réponse à *de quoi ceci dépend-il*. Chaque
  fonction y est tenue aux vecteurs publiés par qui l'a spécifiée — ceux du
  NIST pour SHA-256, ceux de la RFC 4231 pour HMAC, ceux de la RFC 7914 pour
  PBKDF2 — à chaque construction. C'est assez pour dire que les algorithmes
  sont les algorithmes. Ce n'est pas un audit, et ce guide ne prétendra pas que
  c'en est un.

## 17. Ce que le cadriciel ne fera pas

* Il ne parlera à aucune base de données autre que SQLite, et seulement si vous
  la demandez par un second import et `-lsqlite3`.
* Il ne fera pas correspondre les lignes à vos records tout seul. Voir §12.
* Il ne compressera pas. Il ne parlera ni HTTP/2 ni TLS.
* Il ne lira pas un corps de requête en morceaux — il répond **501** et le
  dit.
* Il ne lira pas `multipart/form-data`, donc pas encore d'envoi de fichiers.
* Il n'exécutera pas votre gestionnaire sur un autre fil, donc un gestionnaire
  qui bloque bloque le serveur. Répondez, et revenez.
* Il n'échappera pas ce que vous mettez dans `raw`. C'est à cela que sert le
  nom.

---

## Où sont les choses

| fichier | ce qu'il contient |
|---|---|
| `runtime/kb.h` | toute la surface C : sockets, `poll`, blobs |
| `src/ffi.keal` | le seul fichier qui mentionne le C |
| `src/bytes.keal` | tampons d'octets, hexadécimal, Base64, SHA-1 |
| `src/text.keal` | encodage pour-cent, formulaires, cookies, dates HTTP |
| `src/http.keal` | `Request`, `Response`, le format du fil |
| `src/router.keal` | motifs, correspondance, aiguillage |
| `src/server.keal` | la boucle d'événements et l'automate par connexion |
| `src/ui.keal` | l'arbre de composants et le rendu |
| `src/theme.keal` | la feuille de style et le document |
| `src/json.keal` | JSON dans les deux sens |
| `src/ws.keal` | le tramage WebSocket |
| `src/live.keal` | les sessions, le diff, et le client du navigateur |
| `src/css.keal` | les feuilles de style, écrites en Keal |
| `src/sql.keal` | SQLite : valeurs liées, lignes, transactions, migrations |
| `runtime/kb_sql.h` | le C correspondant, seul à réclamer une bibliothèque |
| `src/upload.keal` | `multipart/form-data`, analysé sur les octets |
| `src/hash.keal` | SHA-256, HMAC, PBKDF2 — avec l'avertissement qui va avec |
| `src/auth.keal` | mots de passe, sessions, gardes, jeton CSRF |
| `src/app.keal` | la porte d'entrée depuis laquelle tout ce qui précède est joignable |
