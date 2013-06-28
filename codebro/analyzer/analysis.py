from django.contrib import messages
from django.db import transaction

from codebro import settings
from .clangparse import ClangParser
from .models import Function, Argument, Xref, Debug


def clang_parse_project(request, project):
    """
    wrapper, used to start xref process
    """
    return generate_project_xref(request, project)


def clang_parse_file(request, project, file):
    """
    wrapper, used to start xref process
    """
    return generate_file_xref(request, project, file)


def add_function_declaration(project, file, data):
    funcname, filename, line, rtype, args = data
    func, created = Function.objects.get_or_create(name = funcname,
                                                   file = file,
                                                   project = project)

    func.line  = line
    func.rtype = rtype
    func.save()
        
    if created:
        args_o = []
        
        for cur_arg_name, cur_arg_type in args:
            arg = Argument()
            arg.name, arg.type = (cur_arg_name, cur_arg_type)
            arg.function = func

        for arg_o in args_o:
                arg_o.save()

    if settings.DEBUG :
        print "%s %s is declared in %s:%d" % (func.name ,
                                              args,
                                              func.file.relative_name,
                                              func.line)

    return


def add_function_call(project, file, data):
    (caller, infos) = data
    caller, created = Function.objects.get_or_create(name = caller,
                                                     file = file,
                                                     project = project)

    callee, created = Function.objects.get_or_create(name = infos["name"],
                                                     file = file,
                                                     project = project)

    xref = Xref()
    xref.project = project
    xref.calling_function = caller
    xref.called_function = callee
    xref.called_function_line = infos['line']

    xref.save()

    if settings.DEBUG :
        print "%s calls %s at %s:%d" % (xref.calling_function.name,
                                        xref.called_function.name,
                                        xref.calling_function.file.relative_name,
                                        xref.called_function_line)
    
    return


@transaction.commit_manually
def generate_file_xref(request, project, file, cparser=None):
    if file.is_parsed:
        return False

    if cparser is None :
        cparser = ClangParser(project)

    try: 
        for out in cparser.get_xref_calls(file.name):
            if len(out) == 5:  # FUNC_DECL
                add_function_declaration(project, file, out)
            
            elif len(out) == 2:  # CALL_EXPR
                add_function_call(project, file, out)

        file.is_parsed = True
        file.save()
        
    except Exception, e:
        if settings.DEBUG:
            print "An exception occured", e
        transaction.rollback()
        return False
    
    else:
        transaction.commit()

    return True
    

def generate_project_xref(request, project):
    """
    generate call xrefs in the project (i.e. on all files), and store them in database
    """
    cparser = ClangParser(project)
    
    for file in project.file_set.all():
        generate_file_xref(request, project, file, cparser)
    
    for cat, fil, lin, error_msg in cparser.diags:
        dbg = Debug()
        dbg.category = cat
        dbg.filepath = fil
        dbg.line = lin
        dbg.message = error_msg
        dbg.project = project
        dbg.save()
        

    project.is_parsed = True
    project.save()
        
    if project.xref_set.count() :
        messages.success(request, "Successfully xref-ed")
        return True
    
    else :
        messages.error(request, "No xref have been established")
        return False

