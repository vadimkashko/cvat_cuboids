import cvat_sdk as cvat
import dash
import plotly.express as px
from dash import Dash, Input, Output, dcc, html
from environs import Env
from PIL import Image, ImageDraw


def calc_fourth_point(*args):
    a, b, c = args
    o = [(a[0] + c[0]) / 2, (a[1] + c[1]) / 2]
    d = (2 * o[0] - b[0], 2 * o[1] - b[1])

    return d


def draw_shapes(image: Image.Image, annotations: dict) -> Image.Image:
    image = image
    draw = ImageDraw.Draw(image)

    line_width = 1
    if image.width * image.height >= 1000000:
        line_width = 2
    elif image.width * image.height >= 3000000:
        line_width = 3

    for shape in annotations:
        if len(shape['attribute']) == 0:
            continue

        points = [[shape['points'][i], shape['points'][i + 1]]
                  for i in range(0, len(shape['points']), 2)]

        if shape['attribute'][0] == '1':
            ftl, fbl, fbr, rbr = points
            ftr = calc_fourth_point(ftl, fbl, fbr)
            rtr = calc_fourth_point(ftr, fbr, rbr)
            rtl = calc_fourth_point(ftl, ftr, rtr)
            rbl = calc_fourth_point(rtl, rtr, rbr)

        elif shape['attribute'][0] == '2':
            ftr, rtr, rbr, rbl = points
            fbr = calc_fourth_point(ftr, rtr, rbr)
            fbl = calc_fourth_point(fbr, rbr, rbl)
            rtl = calc_fourth_point(rtr, rbr, rbl)
            ftl = calc_fourth_point(rtl, rtr, ftr)

        elif shape['attribute'][0] == '3':
            rtl, rbl, fbl, fbr = points
            ftl = calc_fourth_point(rtl, rbl, fbl)
            ftr = calc_fourth_point(ftl, fbl, fbr)
            rtr = calc_fourth_point(rtl, ftl, ftr)
            rbr = calc_fourth_point(rtr, ftr, fbr)

        elif shape['attribute'][0] == '4':
            rtr, rbr, rbl, fbl = points
            rtl = calc_fourth_point(rtr, rbr, rbl)
            ftl = calc_fourth_point(rtl, rbl, fbl)
            ftr = calc_fourth_point(rtr, rtl, ftl)
            fbr = calc_fourth_point(ftr, ftl, fbl)

        rear = [item for sublist in (rtl, rtr, rbr, rbl) for item in sublist]
        left = [item for sublist in (ftl, fbl, rbl, rtl) for item in sublist]
        right = [item for sublist in (ftr, fbr, rbr, rtr) for item in sublist]
        front = [item for sublist in (ftl, ftr, fbr, fbl) for item in sublist]
        first_line = [item for sublist in (ftl, fbr) for item in sublist]
        second_line = [item for sublist in (ftr, fbl) for item in sublist]

        if shape['type'] == 'polyline':
            draw.polygon(rear, outline=shape['color'], width=line_width)
            draw.polygon(left, outline=shape['color'], width=line_width)
            draw.polygon(right, outline=shape['color'], width=line_width)
            draw.polygon(front, outline=shape['color'], width=line_width)
            draw.line(shape['points'], fill='#3d3df5', width=line_width)
            draw.line(first_line, fill='#3d3df5', width=line_width)
            draw.line(second_line, fill='#3d3df5', width=line_width)

    return image


env = Env()
env.read_env('.env')

cvat_host = env.str('CVAT_HOST')
cvat_creds = (env.str('CVAT_USER'), env.str('CVAT_PASSWORD'))

projects_ids = [138, 139]
client = cvat.make_client(cvat_host)
client.login(cvat_creds)

app = Dash(__name__)
server = app.server

projects = [
    client.projects.retrieve(project_id) for project_id in projects_ids
]
projects_ids = [{
    'label': f'{project.id}: {project.name}',
    'value': project.id
} for project in projects]

app.layout = html.Div([
    html.Div(
        [
            html.P('Project select:'),
            dcc.Dropdown(options=projects_ids,
                         value=projects_ids[0]['value'],
                         id="project-id-dropdown",
                         clearable=False,
                         placeholder="Select project",
                         style={
                             'width': 300,
                             'margin': '0 auto'
                         }),
            html.P('Task select:'),
            dcc.Dropdown(id="task-id-dropdown",
                         clearable=False,
                         placeholder="Select task",
                         style={
                             'width': 300,
                             'margin': '0 auto'
                         }),
            html.P('Job select:'),
            dcc.Dropdown(id="job-id-dropdown",
                         clearable=False,
                         placeholder="Select job",
                         style={
                             'width': 300,
                             'margin': '0 auto'
                         }),
            html.P('Выбор фрейма:'),
            dcc.Input(id="frame-id-input",
                      type="number",
                      step=1,
                      placeholder=0,
                      inputMode='numeric',
                      style={
                          'height': 32,
                          'width': 300,
                          'margin': '0 auto'
                      })
        ],
        style={
            'display': 'flex',
            'flex-direction': 'row',
            'justify-content': 'flex-start'
        }),
    html.Div([
        dcc.Slider(0,
                   100,
                   value=0,
                   id='frame-id-slider',
                   tooltip={
                       "placement": "bottom",
                       "always_visible": True
                   })
    ]),
    dcc.Graph(id='image',
              responsive=True,
              config={
                  'fillFrame': True,
                  'autosizable': True,
                  'displayModeBar': True
              }),
    dcc.Store(id='labels', storage_type='session'),
    dcc.Store(id='attributes', storage_type='session'),
    dcc.Store(id='segments', storage_type='session'),
    dcc.Store(id='job-annotations', storage_type='session')
],
                      style={'text-align': 'center'})


@app.callback(Output('task-id-dropdown', 'options'),
              Output('task-id-dropdown', 'value'), Output('labels', 'data'),
              Output('attributes', 'data'),
              Input('project-id-dropdown', 'value'))
def update_task_id_dropdown(selected_project):
    project = client.projects.retrieve(selected_project)
    labels = {label.id: label.to_dict() for label in project.labels}
    attributes = {}
    for label in labels.values():
        for attribute in label['attributes']:
            if attribute['name'] in ['1', '2', '3', '4']:
                attributes[attribute['id']] = attribute['name']

    tasks = [{
        'label': f'{task.id}: {task.name}',
        'value': task.id
    } for task in sorted(project.get_tasks(), key=lambda x: x.id)]

    return tasks, tasks[0]['value'], labels, attributes


@app.callback(Output('job-id-dropdown', 'options'),
              Output('job-id-dropdown', 'value'),
              Output('segments', 'data'),
              Input('task-id-dropdown', 'value'),
              prevent_initial_call=True)
def update_job_id_dropdown(selected_task):
    task = client.tasks.retrieve(selected_task)
    # jobs = sorted([job.id for job in task.get_jobs()])
    segments = {
        segment['jobs'][0]['id']: (
            segment['start_frame'],
            segment['stop_frame'],
        ) for segment in task.segments
    }
    jobs = list(sorted(segments.keys()))

    return jobs, jobs[0], segments


@app.callback(Output('frame-id-input', 'value', allow_duplicate=True),
              Output('frame-id-input', 'min'),
              Output('frame-id-input', 'max'),
              Output('frame-id-slider', 'value', allow_duplicate=True),
              Output('frame-id-slider', 'min'),
              Output('frame-id-slider', 'max'),
              Input('job-id-dropdown', 'value'),
              Input('segments', 'data'),
              prevent_initial_call=True)
def update_frame_id_inputs(selected_job, segments):
    selected_job = str(selected_job)
    start_frame = segments[selected_job][0]
    stop_frame = segments[selected_job][1]
    value = start_frame

    return value, start_frame, stop_frame, value, start_frame, stop_frame


@app.callback(Output('frame-id-input', 'value'),
              Output('frame-id-slider', 'value'),
              Input('frame-id-input', 'value'),
              Input('frame-id-slider', 'value'))
def sync_frame_id_inputs(input_value, slider_value):
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    value = input_value if trigger_id == "frame-id-input" else int(
        slider_value)

    return value, value


@app.callback(Output('job-annotations', 'data'),
              Input('job-id-dropdown', 'value'), Input('labels', 'data'),
              Input('attributes', 'data'))
def get_job_annotations(job_id, labels, attributes):
    job = client.jobs.retrieve(job_id)
    job_annotations = job.get_annotations()
    annotations = {}
    for shape in job_annotations.shapes:
        attribute = [
            attributes[str(attribute.spec_id)]
            for attribute in shape.attributes
            if (attribute.value == 'true') and
            (str(attribute.spec_id) in attributes.keys())
        ]
        frame = shape.frame
        color = labels[str(shape.label_id)]['color']
        points = shape.points
        shape_type = shape.type.value
        id_exists = annotations.get(frame)
        shape_dict = {
            'attribute': attribute,
            'type': shape_type,
            'color': color,
            'points': points
        }
        if not id_exists:
            annotations[frame] = [shape_dict]
        else:
            annotations[frame].append(shape_dict)

    return annotations


@app.callback(Output("image", "figure"), Input('task-id-dropdown', 'value'),
              Input('job-id-dropdown', 'value'),
              Input('frame-id-input', 'value'), Input('job-annotations',
                                                      'data'))
def show_image(task_id, job_id, frame_id, annotations):
    job = client.jobs.retrieve(job_id)
    image = job.get_frame(frame_id, quality='original')
    image = Image.open(image)  # type: ignore
    annotation = annotations.get(str(frame_id))
    if annotation:
        image = draw_shapes(image, annotation)

    figure = px.imshow(
        image,
        labels={
            'x': 'x, points',
            'y': 'y, points'
        },
        title=
        f'''<a href="{cvat_host}/tasks/{task_id}/jobs/{job_id}?frame={frame_id}">To CVAT farme</a>''',
        width=image.width,
        aspect='auto',
        template='seaborn',
    )
    figure.update_layout(autosize=False, width=image.width)

    return figure


if __name__ == '__main__':
    app.run_server(debug=True)
