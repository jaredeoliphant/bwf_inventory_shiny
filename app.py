from arcgis.gis import GIS
import pandas as pd
from dotenv import load_dotenv
import os
from shiny import App, reactive, render, ui
from datetime import date
import bcrypt
from utils import (
    pretty_names,
    rename_to_match_products,
    rename_to_match_db_columns,
    rename_to_match_inv,
)

# to deploy
# rsconnect deploy shiny C:\Users\jared\Documents\brightwater\shinyapps\inventory --name brightwater --title inventory
BASEDIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASEDIR, ".env"))

gis = GIS(
    "https://bwf.maps.arcgis.com/",
    username=os.getenv("UNAME"),
    password=os.getenv("PASSWORD"),
)

ordersFeatureLayer = gis.content.get(os.getenv("INVSURVEY")).layers[0]


def get_raw_orders(as_sdf=True):
    if as_sdf:
        return ordersFeatureLayer.query().sdf
    return ordersFeatureLayer.query().features


def mark_order_complete(order_id):
    features = get_raw_orders(False)
    order_feature = [f for f in features if f.attributes["objectid"] == order_id][0]
    order_feature.attributes["status"] = "Completed"
    order_feature.attributes["when_completed"] = (
        pd.to_datetime("now") - pd.Timestamp("1970-01-01")
    ) // pd.Timedelta("1ms")
    ordersFeatureLayer.edit_features(updates=[order_feature])


inventoryFeatureLayer = gis.content.get(os.getenv("INVDATA")).tables[0]


def get_raw_inventory(as_sdf=True):
    if as_sdf:
        return inventoryFeatureLayer.query().sdf
    return inventoryFeatureLayer.query().features


def add_inventory_item(data):
    # shouldn't be needed
    # parameters
    # data =  {'ShortDesc':'incub_bag',
    #          'LongDesc':'Bag, Incubation',
    #          'Quantity':34,}
    correct_format = {"attributes": data}
    result = inventoryFeatureLayer.edit_features(adds=[correct_format])
    return result


def change_inventory_qty(items_to_change, long=True):
    # parameters
    # items_to_change = {'backpack':4,'incub_bag':276}
    colname = "LongDesc"
    if not long:
        colname = "ShortDesc"
    raw_inv = get_raw_inventory(False)
    final_updates = []
    for k, v in items_to_change.items():
        item_feature = [f for f in raw_inv if f.attributes[colname] == k][0]
        item_feature.attributes["Quantity"] = v
        final_updates.append(item_feature)
    result = inventoryFeatureLayer.edit_features(updates=final_updates)
    return result


def check_inventory_availability(items_dict, long=False):
    # items_dict = {'backpack':5,'incub_bag':6666}
    colname = "LongDesc"
    if not long:
        colname = "ShortDesc"
    inventory = get_raw_inventory()
    issues = []
    for item, qty in items_dict.items():
        inv_qty = inventory.loc[inventory[colname] == item, "Quantity"].iloc[0]
        if qty > inv_qty:
            issues.append(f"{item}: Requested {qty}, Available {inv_qty}")
    return issues


def can_complete_order(order_id):
    orders = get_raw_orders().rename(columns=rename_to_match_products)

    order = orders.loc[orders["order_id"] == order_id].iloc[0]

    items = order.Products.split(",")
    items_dict = {
        rename_to_match_inv[rename_to_match_db_columns[item]]: order[item]
        for item in items
    }

    issues = check_inventory_availability(items_dict)
    if issues:
        return False, issues
    return True, issues


def get_nav_items(logged_in):
    items = [
        ui.nav_panel(
            "Login",
            ui.card(
                ui.input_text("username", "Username:"),
                ui.input_password("password", "Password:"),
                ui.input_action_button("login", "Login"),
                ui.output_text("login_message"),
            ),
        )
    ]

    if logged_in:
        items.extend(
            [
                ui.nav_panel(
                    "Orders",
                    ui.card(
                        ui.card_header("Order List"),
                        ui.input_radio_buttons(
                            "status_filter",
                            "Filter by Status:",
                            choices=["All", "Open", "Completed"],
                            selected="Open",
                            inline=True,
                        ),
                        ui.output_data_frame("order_table"),
                    ),
                    ui.card(
                        ui.card_header("Order Details"),
                        ui.output_ui("order_details"),
                        ui.output_ui("order_edit_form"),
                    ),
                ),
                # Inventory Tab
                ui.nav_panel(
                    "Inventory Management",
                    ui.card(
                        ui.card_header("Current Inventory"),
                        ui.output_data_frame("inventory_table"),
                    ),
                    ui.card(
                        ui.card_header("Update Inventory"),
                        ui.input_select(
                            "item_select",
                            "Select Item",
                            choices=get_raw_inventory()["LongDesc"].tolist(),
                            width="100%",
                        ),
                        ui.input_numeric(
                            "new_quantity", "New Quantity", value=0, min=0, width="100%"
                        ),
                        ui.input_action_button(
                            "update_inventory", "Update", class_="btn-primary w-100"
                        ),
                    ),
                ),
            ]
        )
    return items


app_ui = ui.output_ui("navbar_container")


# app_ui = ui.page_navbar(
#     # ui.navset_tab(
#     # ui.output_image("icon_img", height="60px"),
#     # Orders Tab
#     ui.nav_panel(
#         "Orders",
#         ui.card(
#             ui.card_header("Order List"),
#             ui.input_radio_buttons(
#                 "status_filter",
#                 "Filter by Status:",
#                 choices=["All", "Open", "Completed"],
#                 selected="Open",
#                 inline=True,
#             ),
#             ui.output_data_frame("order_table"),
#         ),
#         ui.card(
#             ui.card_header("Order Details"),
#             ui.output_ui("order_details"),
#             ui.output_ui("order_edit_form"),
#         ),
#     ),
#     # Inventory Tab
#     ui.nav_panel(
#         "Inventory Management",
#         ui.card(
#             ui.card_header("Current Inventory"), ui.output_data_frame("inventory_table")
#         ),
#         ui.card(
#             ui.card_header("Update Inventory"),
#             ui.input_select(
#                 "item_select",
#                 "Select Item",
#                 choices=get_raw_inventory()["LongDesc"].tolist(),
#                 width="100%",
#             ),
#             ui.input_numeric(
#                 "new_quantity", "New Quantity", value=0, min=0, width="100%"
#             ),
#             ui.input_action_button(
#                 "update_inventory", "Update", class_="btn-primary w-100"
#             ),
#         ),
#     ),
# )


def server(input, output, session):
    # Reactive values for data management
    selected_order = reactive.value(None)
    editing_order = reactive.value(False)
    data_version = reactive.value(0)
    logged_in = reactive.value(False)

    @render.image
    def icon_img():
        return {"src": "icon.png", "height": "20px"}

    @output
    @render.ui
    def navbar_container():
        return ui.page_navbar(*get_nav_items(logged_in()), id="nav_panel")

    @output
    @render.text
    def login_message():
        if logged_in():
            return "Logged in successfully!"
        return ""

    @reactive.effect
    @reactive.event(input.login)
    def handle_login():
        users = {
            os.getenv("LOGIN1"): os.getenv("LOGINPASSWORD1"),
            os.getenv("LOGIN2"): os.getenv("LOGINPASSWORD2"),
            os.getenv("LOGIN3"): os.getenv("LOGINPASSWORD3"),
        }
        if bcrypt.checkpw(input.password().encode("utf-8"), users[input.username()].encode("utf-8")):
            logged_in.set(True)
        else:
            ui.notification_show("Invalid login credentials!", type="error")

    @render.data_frame
    def order_table():
        # df = orders_rv.get()
        data_version()
        df = (
            get_raw_orders()
            .rename(
                columns={
                    "objectid": "Order #",
                    "Namebwe": "Player-Coach",
                    # "ReceivingSWE": "SWE",
                    "status": "Status",
                }
            )
            .assign(Date=lambda df_: df_.Date.dt.strftime("%d %b, %Y"))
            .assign(SWE=lambda df_: df_.ReceivingSWE.str.split(" - ").str[-1])
        )
        if input.status_filter() != "All":
            df = df[df["Status"] == input.status_filter()]
        return render.DataTable(
            df[["Order #", "Player-Coach", "Date", "SWE", "Community", "Status"]],
            height="500px",
            row_selection_mode="single",
        )

    @render.ui
    def order_details():
        data_version()
        selected = input.order_table_selected_rows()
        if not selected:
            return ui.p("Select an order to view details")
        if editing_order():
            return None

        df = get_raw_orders().rename(columns=rename_to_match_products)
        if input.status_filter() != "All":
            df = df[df["status"] == input.status_filter()]

        order = df.iloc[selected[0]]

        detail_ui = ui.div(
            ui.h4(f"Order #{order['order_id']}"),
            ui.p(f"Player Coach: {order['Namebwe']}"),
            ui.p(f"SWE: {order['ReceivingSWE'].split(' - ')[-1]}"),
            ui.p(f"Community: {order['Community']}"),
            ui.p(f"Date: {order['Date'].strftime('%d %b, %Y')}"),
            ui.p(f"Status: {order['status']}"),
            ui.p(ui.strong("Items:")),
            ui.tags.ul(
                [
                    ui.tags.li(f"{pretty_names.get(item,item)}: {order[item]} units")
                    for item in order["Products"].split(",")
                ]
            ),
        )

        if order["status"] == "Open":
            detail_ui.children.extend(
                [
                    ui.input_action_button(
                        "edit_order",
                        "Edit Order",
                        class_="w-100",
                    ),
                    ui.input_action_button(
                        f"complete_{order['order_id']}",
                        "Mark as Completed",
                        class_="btn-success w-100",
                    ),
                ]
            )

        if order["status"] == "Completed":
            detail_ui.children.extend(
                [
                    ui.p(
                        f"Completed Date: {order['when_completed'].strftime('%d %b, %Y')}"
                    ),
                ]
            )
        return detail_ui

    @render.ui
    def order_edit_form():
        selected = input.order_table_selected_rows()
        if not selected:
            return None
        if not editing_order():
            return None

        df = get_raw_orders().rename(columns=rename_to_match_products)
        if input.status_filter() != "All":
            df = df[df["status"] == input.status_filter()]

        order = df.iloc[selected[0]]

        items = order.Products.split(",")
        items_dict = {item: order[item] for item in items}

        return ui.div(
            ui.h5(f"Edit Order #{order.order_id}"),
            *[
                ui.input_numeric(
                    f"edit_item_{item}",
                    f"Quantity for {pretty_names[item]}:",
                    value=int(items_dict[item]),
                )
                for item in items_dict.keys()
            ],
            ui.input_action_button("save_changes", "Save Changes"),
            ui.input_action_button("cancel_edit", "Cancel"),
        )

    @reactive.effect
    @reactive.event(input.edit_order)
    def handle_edit_start():
        editing_order.set(True)

    @reactive.effect
    @reactive.event(input.cancel_edit)
    def handle_edit_cancel():
        editing_order.set(False)

    @reactive.effect
    @reactive.event(input.save_changes)
    def handle_save_changes():
        selected = input.order_table_selected_rows()
        if not selected:
            return None

        df = get_raw_orders().rename(columns=rename_to_match_products)
        if input.status_filter() != "All":
            df = df[df["status"] == input.status_filter()]

        order = df.iloc[selected[0]]

        items_dict = {}

        # Collect all item quantities from form
        for item in order.Products.split(","):
            qty = getattr(input, f"edit_item_{item}")()
            if qty != order[item]:
                items_dict[item] = qty

        if items_dict:
            order_id = order.order_id
            features = get_raw_orders(False)
            order_feature = [
                f for f in features if f.attributes["objectid"] == order_id
            ][0]

            order_feature.attributes["order_edited"] = "Yes"
            order_feature.attributes["last_edited"] = (
                pd.to_datetime("now") - pd.Timestamp("1970-01-01")
            ) // pd.Timedelta("1ms")

            for k, v in items_dict.items():
                order_feature.attributes[rename_to_match_db_columns[k]] = v

            ordersFeatureLayer.edit_features(updates=[order_feature])

            data_version.set(data_version() + 1)
            editing_order.set(False)
            ui.notification_show("Order updated successfully!", duration=3)
        else:
            editing_order.set(False)
            ui.notification_show("No Change to Order", duration=3)

    @render.data_frame
    def inventory_table():
        data_version()
        return render.DataTable(
            (
                get_raw_inventory()
                .loc[:, ["LongDesc", "Quantity"]]
                .rename(columns={"LongDesc": "Item Description"})
            ),
            width="450px",
        )

    def update_inventory_count():
        item = input.item_select()
        new_quantity = input.new_quantity()
        change_inventory_qty({item: new_quantity})
        ui.notification_show(
            f"Updated {item} quantity to {new_quantity}", type="message", duration=3
        )

    @reactive.effect
    @reactive.event(input.update_inventory)
    def _():
        item = input.item_select()
        new_quantity = input.new_quantity()
        inv = get_raw_inventory()
        current_quantity = inv.loc[inv["LongDesc"] == item, "Quantity"].iloc[0]

        ui.modal_show(
            ui.modal(
                f"Are you sure you want to update the inventory count for {item}?",
                ui.p(
                    f'Change "{item}" quantity from {current_quantity} to {new_quantity}?'
                ),
                ui.p(
                    "This action will update the inventory count immediately so please be sure it is correct."
                ),
                title="Confirm Inventory Update",
                easy_close=True,
                footer=ui.div(
                    ui.input_action_button(
                        "confirm_update", "Yes, Update", class_="btn-primary"
                    ),
                    ui.input_action_button(
                        "cancel_update", "Cancel", class_="btn-secondary"
                    ),
                ),
            )
        )

    @reactive.effect
    @reactive.event(input.confirm_update)
    def _():
        update_inventory_count()
        # Increment the reactive value to trigger table refresh
        data_version.set(data_version() + 1)
        ui.modal_remove()

    @reactive.effect
    @reactive.event(input.cancel_update)
    def _():
        ui.modal_remove()

    # Handle order completion buttons
    def create_order_complete_handler(order_id):
        @reactive.effect
        @reactive.event(lambda: input[f"complete_{order_id}"]())
        def _():
            # check to see if order can be fulfilled as is...
            move_forward, issues = can_complete_order(order_id)
            if move_forward:
                ui.modal_show(
                    ui.modal(
                        f"Are you sure you want to mark Order # {order_id} Complete?",
                        ui.p(
                            f"Orders should be marked complete when the items leave the Warehouse (Learning Center)"
                        ),
                        ui.p("This action will automatically update the inventory"),
                        title="Confirm Order Completion",
                        easy_close=True,
                        footer=ui.div(
                            ui.input_action_button(
                                f"confirm_order_{order_id}",
                                "Yes, complete the order and update inventory",
                                class_="btn-primary",
                            ),
                            ui.input_action_button(
                                "cancel_order", "Cancel", class_="btn-secondary"
                            ),
                        ),
                    )
                )
            else:
                ui.modal_show(
                    ui.modal(
                        f"There are not enough items in inventory to fulfill this order.",
                        ui.p(
                            f"The order can be edited to lower the number of items in the order"
                        ),
                        ui.div(
                            ui.tags.ul([ui.tags.li(f"{issue}") for issue in issues]),
                        ),
                        title="Order Cannot Be Completed",
                        easy_close=True,
                    )
                )

    # Create handlers for all possible order IDs
    for order_id in get_raw_orders()["objectid"]:
        create_order_complete_handler(order_id)

    # Handle order completion confirmation buttons
    def create_order_confirmation_handler(order_id):
        @reactive.effect
        @reactive.event(lambda: input[f"confirm_order_{order_id}"]())
        def _():
            mark_order_complete(order_id)
            orders = get_raw_orders().rename(columns=rename_to_match_products)

            order = orders.loc[orders["order_id"] == order_id].iloc[0]

            items = order.Products.split(",")
            items_dict = {item: order[item] for item in items}

            inv_dict = (
                get_raw_inventory().set_index("ShortDesc").loc[:, "Quantity"].to_dict()
            )

            items_to_change = {}

            for k, v in items_dict.items():
                inv_name = rename_to_match_inv[rename_to_match_db_columns[k]]
                current_inv = inv_dict[inv_name]
                new_inv = current_inv - v
                # print(k, inv_name, current_inv, new_inv)
                items_to_change[inv_name] = new_inv

            change_inventory_qty(items_to_change, long=False)
            # Increment the reactive value to trigger table refresh
            data_version.set(data_version() + 1)
            # Get customer name for the notification
            customer = order.loc["Namebwe"]
            ui.notification_show(
                f"Order #{order_id} for {customer} marked as completed",
                type="message",
                duration=3,
            )
            ui.modal_remove()

    # Create confirmation handlers for all possible order IDs
    for order_id in get_raw_orders()["objectid"]:
        create_order_confirmation_handler(order_id)

    @reactive.effect
    @reactive.event(input.cancel_order)
    def _():
        ui.modal_remove()


app = App(app_ui, server)
