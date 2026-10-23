"""19.0.1.0.0 -> 19.0.1.1.0: routing rules become a flow of steps.

Each form gets a Start step followed by its rules in the order they used to
run: "inform when sent", then the approvals, then "inform when approved". A
rule with conditions gets a Condition step in front of it whose "no" branch
skips it. Steps of requests in progress point at the new flow steps; the ones
that were only waiting are dropped, the flow creates them again when reached.

The old tables are still there at this point (Odoo drops them afterwards).
"""
from odoo import SUPERUSER_ID, api

GAP_X = 260
ROW_Y = 200


def migrate(cr, version):
    cr.execute("SELECT to_regclass('angels_form_rule')")
    if not cr.fetchone()[0]:
        return
    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
    Node = env["angels.form.node"].with_context(angels_flow_defer=True)
    node_by_rule = {}
    order = {"notify_submit": 0, "approve": 1, "notify_done": 2}

    def create_node(vals, names):
        """``names`` is the stored translations of the rule name, by language."""
        node = Node.create(dict(vals, name=names.get("en_US") or next(iter(names.values()), "")))
        for lang, name in names.items():
            if lang != "en_US":
                node.with_context(lang=lang).name = name
        return node

    for form in env["angels.form"].search([]):
        if form.node_ids:
            # The example form gets its flow from the module data.
            continue
        cr.execute("""
            SELECT id, name, rule_type, assign_type, group_id, user_field_id, approval_rule, condition_match
              FROM angels_form_rule
             WHERE form_id = %s
          ORDER BY sequence, id
        """, [form.id])
        rules = sorted(cr.dictfetchall(), key=lambda r: order.get(r["rule_type"], 1))
        x = 40
        start = Node.create({"form_id": form.id, "name": "Request Sent", "node_type": "start",
                             "pos_x": x, "pos_y": ROW_Y})
        # Outputs that lead to whatever comes next: (node, link field).
        loose = [(start, "next_id")]

        def attach(target):
            for node, link in loose:
                node[link] = target

        for color, rule in enumerate(rules, start=1):
            names = rule["name"] if isinstance(rule["name"], dict) else {"en_US": rule["name"] or ""}
            cr.execute(
                "SELECT res_users_id FROM angels_form_rule_res_users_rel WHERE angels_form_rule_id = %s",
                [rule["id"]],
            )
            user_ids = [row[0] for row in cr.fetchall()]
            cr.execute("SELECT count(*) FROM angels_form_condition WHERE rule_id = %s", [rule["id"]])
            has_conditions = cr.fetchone()[0]
            if has_conditions:
                x += GAP_X
                condition = create_node({
                    "form_id": form.id,
                    "node_type": "condition",
                    "condition_match": rule["condition_match"] or "all",
                    "pos_x": x,
                    "pos_y": ROW_Y,
                }, {lang: f"{name}?" for lang, name in names.items()})
                cr.execute(
                    "UPDATE angels_form_condition SET node_id = %s, rule_id = NULL WHERE rule_id = %s",
                    [condition.id, rule["id"]],
                )
                attach(condition)
            x += GAP_X
            node = create_node({
                "form_id": form.id,
                "node_type": "approve" if rule["rule_type"] == "approve" else "notify",
                "assign_type": rule["assign_type"] or "users",
                "user_ids": [(6, 0, user_ids)],
                "group_id": rule["group_id"],
                "user_field_id": rule["user_field_id"],
                "approval_rule": rule["approval_rule"] or "any",
                "color": color,
                "pos_x": x,
                "pos_y": ROW_Y - 120 if has_conditions else ROW_Y,
            }, names)
            if has_conditions:
                condition.yes_id = node
                loose = [(condition, "no_id"), (node, "next_id")]
            else:
                attach(node)
                loose = [(node, "next_id")]
            node_by_rule[rule["id"]] = node.id

        x += GAP_X
        end = Node.create({"form_id": form.id, "name": "Approved", "node_type": "end",
                           "end_state": "approved", "pos_x": x, "pos_y": ROW_Y})
        attach(end)

    # Steps of existing requests.
    for rule_id, node_id in node_by_rule.items():
        cr.execute("UPDATE angels_form_step SET node_id = %s WHERE rule_id = %s", [node_id, rule_id])
    # Steps of the example form: its flow has steps with the same names.
    cr.execute("""
        UPDATE angels_form_step step
           SET node_id = node.id
          FROM angels_form_submission submission, angels_form_node node
         WHERE step.node_id IS NULL
           AND submission.id = step.submission_id
           AND node.form_id = submission.form_id
           AND node.node_type IN ('approve', 'notify')
           AND node.name ->> 'en_US' = step.name
    """)
    cr.execute("DELETE FROM angels_form_step WHERE state = 'waiting'")
    cr.execute("""
        UPDATE angels_form_step SET step_type = 'notify'
         WHERE step_type IN ('notify_submit', 'notify_done')
    """)

    # Conditions of rules that were not converted (the example form) go away.
    cr.execute("""
        DELETE FROM angels_form_condition
         WHERE rule_id IS NOT NULL AND node_id IS NULL AND field_id IS NULL
     RETURNING id
    """)
    removed = [row[0] for row in cr.fetchall()]
    if removed:
        cr.execute(
            "DELETE FROM ir_model_data WHERE model = 'angels.form.condition' AND res_id IN %s",
            [tuple(removed)],
        )
    cr.execute("DELETE FROM ir_model_data WHERE model = 'angels.form.rule'")
